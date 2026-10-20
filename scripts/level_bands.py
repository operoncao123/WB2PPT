#!/usr/bin/env python3
"""Level Western-blot band rows: measure each band row's tilt, rotate the raw
scan flat, verify by re-measurement, and report before/after geometry as JSON.

Bands that drift up or down across a panel are leveled by rotating the raw ECL
scan BEFORE cropping (user requirement: all bands on a horizontal line). The
least-squares line through the per-lane band y-centers is the rotation that
minimizes squared y-deviations, so its angle is what gets applied; a panel with
several band rows (e.g. precursor + mature) can show DIFFERENT tilts (gel
distortion, not a rigid tilt — real case: -5.2° vs -3.7°). The mean angle is
applied and per-row residual slopes are reported. Disclose the rotation on the
slide (info-block line) — raw-data records must note digital processing.

Usage:
  python3 level_bands.py --src RAW_ECL.Tif --out ROTATED.tif \
      --row "1055,1110:862,959,1056,1153" \
      --row "1240,1300:862,959,1056,1153" \
      [--fill 255] [--half 32] [--json level.json]

- --row "y0,y1:x1,x2,..." — y-range containing ONE band row (pre-rotation,
  native px), then the lane x-centers. Repeat per band row; all rows should
  share the same lane-center list.
- PIL convention trap: rotate(angle) positive = COUNTERCLOCKWISE (visual).
  A row with slope b (y vs x, y down) is leveled by rotate(degrees(atan(b))):
  rising-to-right rows (b<0) get the negative (clockwise) angle. Negating the
  angle doubles the tilt instead of leveling it. The script re-measures the
  rotated image and exits 1 if any row got worse (sign flip or lost row).
- Rotation moves EVERYTHING: lane x-centers, band y-centers, membrane edges.
  Re-derive crop boxes, lane_fracs and tick_frac from the ROTATED image. To
  re-locate lanes, transform the pre-rotation lane grid through the rotation
  about the image center (rigid transform preserves spacing) and refine in
  small local windows; re-segmenting from scratch tends to merge lanes because
  bicubic resampling raises the between-lane valleys.
- Out-of-bounds corners after rotation are filled white (ECL background).

Output JSON: per row, before/after {y_centers, slope, angle_deg} plus the
residual rise in px across the lane span, and the applied angle.
"""

import argparse
import json
import math
import sys

import numpy as np
from PIL import Image


def load_gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=float)


def row_ycenters(img, y0, y1, xs, half, floor=5):
    """Intensity-weighted band y-center in a window around each lane center."""
    ys = np.arange(y0, y1)
    out = []
    for x in xs:
        prof = 255.0 - img[y0:y1, int(x - half):int(x + half)]
        w = np.clip(prof - (np.median(prof) + floor), 0, None)
        out.append(float((ys[:, None] * w).sum() / w.sum()) if w.sum() else None)
    return out


def fit_row(yc, xs):
    """LSQ slope/angle over the rows that produced a measurement."""
    pairs = [(x, y) for x, y in zip(xs, yc) if y is not None]
    if len(pairs) < 2:
        return None
    xa = np.array([p[0] for p in pairs], float)
    ya = np.array([p[1] for p in pairs], float)
    b, a = np.polyfit(xa, ya, 1)
    return {"xs": xa.tolist(), "y_centers": ya.tolist(),
            "slope": float(b), "angle_deg": math.degrees(math.atan(b)),
            "span_px": float(xa.max() - xa.min())}


def measure(img, rows, half, expand=0):
    res = []
    for (y0, y1), xs in rows:
        fit = fit_row(row_ycenters(img, y0 - expand, y1 + expand, xs, half), xs)
        res.append(fit)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True, help="rotated full image to write")
    ap.add_argument("--row", required=True, action="append", default=[],
                    help='"y0,y1:x1,x2,..." band-row range + lane x-centers (repeatable)')
    ap.add_argument("--fill", type=int, default=255, help="fill for rotated corners")
    ap.add_argument("--half", type=int, default=32, help="half-window around each lane center")
    ap.add_argument("--json", help="write before/after report here")
    args = ap.parse_args()

    rows = []
    for spec in args.row:
        rng, xs = spec.split(":")
        y0, y1 = (int(v) for v in rng.split(","))
        rows.append(((y0, y1), [int(v) for v in xs.split(",")]))

    img = load_gray(args.src)
    pre = measure(img, rows, args.half)
    angles = [f["angle_deg"] for f in pre if f]
    if not angles:
        sys.exit("no band row produced >=2 lane measurements — check the --row windows")
    angle = float(np.mean(angles))

    im = Image.open(args.src).convert("L")
    rot = im.rotate(angle, resample=Image.BICUBIC, fillcolor=args.fill)
    rot.save(args.out)

    # rows shift vertically by ~|sin(angle)| * max|x - image center|; expand windows
    cx = img.shape[1] / 2
    max_off = max(max(abs(x - cx) for x in xs) for _, xs in rows)
    expand = int(math.ceil(abs(math.sin(math.radians(angle))) * max_off)) + 15
    post = measure(load_gray(args.out), rows, args.half, expand=expand)

    report = {"src": args.src, "out": args.out, "applied_angle_deg": round(angle, 3),
              "rows": []}
    failed = False
    for i, (f_pre, f_post) in enumerate(zip(pre, post)):
        entry = {"row": i, "before": f_pre, "after": f_post}
        if f_pre and f_post:
            entry["residual_rise_px"] = round(f_post["slope"] * f_post["span_px"], 1)
            if abs(f_post["angle_deg"]) > abs(f_pre["angle_deg"]):
                entry["problem"] = ("row got WORSE after rotation — sign flipped or "
                                    "window lost the row; do not use this output")
                failed = True
        elif f_post is None:
            entry["problem"] = "row not found in the expanded post-rotation window"
            failed = True
        report["rows"].append(entry)
        tag = f_pre["angle_deg"] if f_pre else float("nan")
        res = entry.get("residual_rise_px", "?")
        print(f"row {i}: angle {tag:+.2f} deg -> "
              f"{f_post['angle_deg'] if f_post else float('nan'):+.2f} deg "
              f"(residual rise {res} px over span)")

    if args.json:
        json.dump(report, open(args.json, "w"), indent=1)
    if failed:
        sys.exit(json.dumps(report, indent=1))
    print(f"applied rotate({angle:+.3f}); rotated image -> {args.out}")


if __name__ == "__main__":
    main()
