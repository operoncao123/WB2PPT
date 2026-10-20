#!/usr/bin/env python3
"""Lane-grid cross-check between two panels of the SAME gel (cut-membrane WB).

Why: analyze_scan.py --lanes N fills a shortfall of detected x-runs by evenly
splitting the detected span into N windows. Weak lanes below threshold shrink the
span, the split windows drift, outer lanes fall outside and get cropped, and every
per-lane stat sampled there is mis-assigned (real case 20261012: Cas9 panel lost
clone 13, clone 9 misread as negative).

This tool takes the clean panel of the same gel as the grid reference, fits
x_target = a*x_ref + b on confidently detected columns, predicts ALL lane centers
on the target panel, and recommends a crop box that covers the full grid so stacked
panels align.

Usage:
  python3 check_lane_grid.py \
    --ref-ecl IM_actin.Tif  --ref-band-y 1030,1130 \
    --ecl     IM_cas9.Tif   --band-y     1040,1300 \
    --n-lanes 13 --margin 20 --out grid_check.json

Output JSON: reference/target run centers per threshold, fitted a/b/rmse, predicted
lane centers, recommended crop box, lane_fracs, warnings[].
Exit code 1 if warnings suggest the naive windows are unsafe.
"""
import argparse
import json

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert("L"), dtype=float)


def col_runs(im, y0, y1, x0, x1, th, min_w=25):
    p = im[y0:y1, x0:x1].mean(axis=0)
    dark = p < np.median(p) - th
    runs, i = [], 0
    while i < len(dark):
        if dark[i]:
            j = i
            while j < len(dark) and dark[j]:
                j += 1
            if j - i >= min_w:
                runs.append((x0 + i, x0 + j))
            i = j
        else:
            i += 1
    return runs


def detect_centers(im, y0, y1, n_lanes, ths=(6, 5, 4, 3, 2.5)):
    """Sweep thresholds; return (centers, per-th runs) of the best pass."""
    best = ([], None)
    for th in ths:
        runs = col_runs(im, y0, y1, 300, im.shape[1] - 60, th)
        centers = [(a + b) / 2 for a, b in runs]
        if len(centers) > len(best[0]):
            best = (centers, (th, runs))
        if len(centers) >= n_lanes:
            return centers, (th, runs)
    return best


def merge_close(centers, tol):
    """Merge detected centers closer than tol (split peaks of one lane)."""
    out = []
    for c in sorted(centers):
        if out and c - out[-1][-1] < tol:
            out[-1].append(c)
        else:
            out.append([c])
    return [sum(g) / len(g) for g in out]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref-ecl", required=True, help="clean panel of the same gel (grid reference)")
    ap.add_argument("--ref-band-y", required=True, help="y0,y1 band rows of the reference panel")
    ap.add_argument("--ecl", required=True, help="target panel ECL")
    ap.add_argument("--band-y", required=True, help="y0,y1 band rows of the target panel")
    ap.add_argument("--n-lanes", type=int, required=True)
    ap.add_argument("--margin", type=int, default=20, help="horizontal crop margin px")
    ap.add_argument("--crop-y", default=None, help="y0,y1 for the recommended crop (default: --band-y)")
    ap.add_argument("--out", default="grid_check.json")
    args = ap.parse_args()

    ref = load(args.ref_ecl)
    tgt = load(args.ecl)
    ry0, ry1 = (int(v) for v in args.ref_band_y.split(","))
    ty0, ty1 = (int(v) for v in args.band_y.split(","))
    N = args.n_lanes
    warns = []

    # ---- reference grid ----
    rc, refinfo = detect_centers(ref, ry0, ry1, N)
    rc = merge_close(rc, 0.5 * (np.median(np.diff(sorted(rc))) if len(rc) > 2 else 60))
    sp = np.diff(rc) if len(rc) > 1 else np.array([0])
    sp_med = float(np.median(sp)) if len(sp) else 0.0
    if len(rc) != N:
        warns.append(f"reference panel: {len(rc)} columns != {N} lanes; "
                     f"reconstructing even grid (spacing {sp_med:.0f}) anchored at span center")
        anchor = float(np.median(rc))
        rc = [anchor + (k - (N - 1) / 2) * sp_med for k in range(N)]
    if sp_med and len(sp) > 2 and float(np.std(sp)) / sp_med > 0.08:
        warns.append(f"reference spacing uneven (std/med={float(np.std(sp))/sp_med:.2f}); check manually")

    # ---- target: sweep thresholds, then fit a,b against reference grid ----
    tc, tgtinfo = detect_centers(tgt, ty0, ty1, N)
    tc = merge_close(tc, sp_med * 0.5) if sp_med else tc

    # Initial (a,b) from detected-to-detected offset voting. A near-uniform grid can
    # match an integer number of lanes off with a similar inlier count, so
    # median-to-median or even inlier-count maximization on synthetic grids is
    # ambiguous; real column positions voting on the offset cannot.
    votes = [t - r for r in rc for t in tc]
    best = (0, 1.0, 0.0)
    for v in votes:
        cluster = [d for d in votes if abs(d - v) < sp_med / 3]
        if len(cluster) > best[0]:
            best = (len(cluster), 1.0, float(np.median(cluster)))
    _, _, b0 = best
    if best[0] < 3:
        warns.append(f"offset voting weak ({best[0]} votes): panels share few clear columns, verify overlay manually")

    def match(a, b, win):
        pairs, used = {}, set()
        for t in tc:
            d = [abs(t - (a * r + b)) for r in rc]
            k = int(np.argmin(d))
            if d[k] < win and k not in used:
                pairs[k] = (rc[k], t)
                used.add(k)
        return [pairs[k] for k in sorted(pairs)]

    a, b = 1.0, b0
    matched = []
    for _ in range(3):
        pairs = match(a, b, sp_med * 0.3)
        if len(pairs) >= 2:
            xs = np.array([p[0] for p in pairs])
            ys = np.array([p[1] for p in pairs])
            fa, fb = np.polyfit(xs, ys, 1)
            if 0.97 <= fa <= 1.03:
                a, b = float(fa), float(fb)
            else:
                warns.append(f"fitted scale a={fa:.4f} outside [0.97,1.03], clamped to 1.0")
                a, b = 1.0, float(np.mean([t - r for r, t in pairs]))
        matched = pairs

    pred = [a * r + b for r in rc]
    resid = [t - (a * r + b) for r, t in matched]
    rmse = float(np.sqrt(np.mean(np.square(resid)))) if resid else -1

    # coverage: how many predicted centers have a detected column nearby
    cov = sum(1 for p in pred if any(abs(t - p) < sp_med * 0.35 for t in tc))
    note = f"{cov}/{N} lanes have detectable signal (silent lanes predicted from grid; normal for weak clones)"
    if abs(a - 1.0) > 0.03:
        warns.append(f"scale a={a:.4f} deviates from 1 by >3% — suspect an artifact, verify before trusting")
    # detected-span coverage check: naive even split would have used this span
    if tc and (max(tc) - min(tc)) < (N - 1) * sp_med * 0.92:
        warns.append("detected span under-covers the full grid: analyze_scan even-split windows WOULD have drifted")

    cy = args.crop_y or args.band_y
    cy0, cy1 = (int(v) for v in cy.split(","))
    x0 = int(pred[0] - sp_med / 2) - args.margin
    x1 = int(pred[-1] + sp_med / 2) + args.margin
    fracs = [round((c - x0) / (x1 - x0), 4) for c in pred]

    res = {
        "n_lanes": N,
        "ref": {"file": args.ref_ecl, "centers": [round(c, 1) for c in rc],
                "threshold_used": refinfo[0] if refinfo else None},
        "target": {"file": args.ecl, "detected_centers": [round(c, 1) for c in tc],
                   "threshold_used": tgtinfo[0] if tgtinfo else None,
                   "detected_coverage": note},
        "fit": {"a": round(float(a), 5), "b": round(float(b), 1), "rmse_px": round(rmse, 2),
                "matched_columns": len(matched)},
        "predicted_centers": [round(c, 1) for c in pred],
        "crop_box": [x0, cy0, x1, cy1],
        "lane_fracs": fracs,
        "warnings": warns,
    }
    json.dump(res, open(args.out, "w"), indent=1)
    print(f"fit x_t = {a:.5f}*x_r + {b:.1f}   rmse={rmse:.1f}px on {len(matched)} columns")
    print(f"predicted {N} centers: {[round(c) for c in pred]}")
    print(f"crop_box = [{x0},{cy0},{x1},{cy1}]   ({note})")
    for w in warns:
        print("WARN:", w)
    if warns:
        raise SystemExit(1)
    print("OK: use predicted centers / lane_fracs; re-sample band stats at these windows.")


if __name__ == "__main__":
    main()
