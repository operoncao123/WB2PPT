#!/usr/bin/env python3
"""Analyze a raw Western blot imager scan: membrane extent, ladder dips, lanes, bands.

Outputs a blot-map JSON and an annotated overlay PNG for user confirmation.

Usage:
  python3 analyze_scan.py --ecl PATH [--marker PATH] [--merge PATH]
      [--ladder 180,135,100,75,65,45,35,25,15,10]
      [--anchor "Cas9=160"] [--anchor "Actin=42"]     # repeatable
      [--lanes 4]                                      # expected lane count (default: auto)
      [--band-y 1050,1180]                             # y-range containing the bands (ECL)
      [--ladder-x 548,615]                             # x-window of the ladder lane (marker)
      [--invert]                                       # ECL stored as white-bands-on-black
      --out blot_map.json [--overlay overlay.png]

All coordinates are in native scan pixels (origin = top-left of the image).
"""

import argparse
import json
import sys

import numpy as np
from PIL import Image, ImageDraw


def load_gray(path, invert=False):
    a = np.array(Image.open(path).convert("L"), dtype=float)
    return 255.0 - a if invert else a


def membrane_extent(img, x_probe=(0.35, 0.90), thresh=100):
    """Bright membrane rows against dark background (marker channel)."""
    H, W = img.shape
    prof = img[:, int(x_probe[0] * W):int(x_probe[1] * W)].mean(axis=1)
    rows = np.where(prof > thresh)[0]
    return (int(rows.min()), int(rows.max())) if len(rows) else None


def find_dips(prof, min_depth=4, min_w=6, merge_gap=8, drop_boundary=True):
    """Dark dips vs local background: return [(center, depth, w0, w1)].

    Runs touching the first/last index are membrane-edge transitions, not bands,
    and are dropped when drop_boundary=True.
    """
    bg = np.median(prof)
    mask = (bg - prof) > min_depth
    runs = []
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if j - i >= min_w:
                if drop_boundary and (i == 0 or j == len(mask)):
                    i = j
                    continue
                seg = prof[i:j]
                w = bg - seg
                c = float((np.arange(i, j) * w).sum() / w.sum())
                runs.append((round(c, 1), round(float(bg - seg.min()), 1), i, j))
            i = j
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and r[2] - merged[-1][3] < merge_gap:
            p = merged[-1]
            merged[-1] = (round((p[0] + r[0]) / 2, 1), max(p[1], r[1]), p[2], r[3])
        else:
            merged.append(list(r) if isinstance(r, list) else r)
    return [tuple(r) for r in merged]


def ladder_bands(marker, mem_y, ladder_x=None, edge_inset=15):
    """Detect ladder dips inside the membrane, in the ladder x-window.

    The first/last `edge_inset` rows inside the membrane are excluded: the
    dark->bright transition at the membrane edges otherwise reads as huge dips.
    Returned dip centers are ABSOLUTE image y.
    """
    y0, y1 = mem_y[0] + edge_inset, mem_y[1] - edge_inset
    if ladder_x:
        win = [(int(ladder_x[0]), int(ladder_x[1]))]
    else:
        # heuristic: candidate 70px windows across the left half; keep those with most dips
        win = [(x, x + 70) for x in range(300, marker.shape[1] // 2, 25)]
    scored = []
    for x0, x1 in win:
        prof = marker[y0:y1, x0:x1].mean(axis=1)
        dips = find_dips(prof, min_depth=3)
        abs_dips = [(round(c + y0, 1), dep, a, b) for c, dep, a, b in dips]
        scored.append((len(abs_dips), -sum(d[1] for d in abs_dips), x0, x1, abs_dips))
    scored.sort(key=lambda t: (-t[0], t[1]))
    n, _, x0, x1, dips = scored[0]
    return {"x_window": [x0, x1], "dips": dips}


def assign_ladder(obs_ys, ladder, mem_y=None, anchors=None, ecl_band_ys=None):
    """Enumerate consecutive slices of the ladder vs observed ys; fit y = a + b*log10(MW).

    y grows downward while MW shrinks, so a valid assignment has b > 0.
    If membrane extent (mem_y) and anchors {name: expected_mw} are given, candidates whose
    predicted anchor position falls outside the membrane are REJECTED.
    Each candidate also records the distance from its predicted anchor y to the nearest
    observed ECL band center (ecl_band_ys) — the strongest ranking signal.
    Returns candidates sorted by (anchor_dist, rmse).
    """
    n = len(obs_ys)
    cands = []
    for i in range(0, len(ladder) - n + 1):
        seg = ladder[i:i + n]
        x = np.log10(np.array(seg, dtype=float))
        y = np.array(obs_ys, dtype=float)
        b, a = np.polyfit(x, y, 1)
        # migration: y = a + b*log10(MW) with b < 0 (larger MW runs higher, i.e. smaller y)
        if b >= 0:
            continue
        rmse = float(np.sqrt(np.mean((a + b * x - y) ** 2)))
        cand = {"offset": i, "values": seg, "rmse": round(rmse, 2),
                "px_per_decade": round(float(-b), 1),
                "fit": {"a": round(float(a), 1), "b": round(float(b), 1)}}
        ok = True
        if mem_y:
            cand["anchor_pred"] = {}
            dists = []
            for name, mw in (anchors or {}).items():
                py = float(a + b * np.log10(mw))
                cand["anchor_pred"][name] = round(py, 1)
                if not (mem_y[0] - 30 <= py <= mem_y[1] + 30):
                    ok = False
                if ecl_band_ys:
                    dists.append(min(abs(py - by) for by in ecl_band_ys if by is not None) if ecl_band_ys else None)
            if dists and all(d is not None for d in dists):
                cand["anchor_band_dist_px"] = round(float(max(dists)), 1)
        if ok:
            cands.append(cand)
    cands.sort(key=lambda d: (d.get("anchor_band_dist_px", 0), d["rmse"]))
    return cands


def mw_to_y(fit, mw):
    a, b = fit["a"], fit["b"]
    return a + b * np.log10(mw)


def detect_lanes(ecl, band_y, n_lanes=None, min_w=30, depth=5):
    xprof = ecl[band_y[0]:band_y[1], :].mean(axis=0)
    bg = np.median(xprof)
    dark = xprof < bg - depth
    runs, i = [], 0
    while i < len(dark):
        if dark[i]:
            j = i
            while j < len(dark) and dark[j]:
                j += 1
            if j - i >= min_w:
                runs.append([i, j])
            i = j
        else:
            i += 1
    # split wide runs into n_lanes windows if lane count known and runs merged
    if n_lanes and len(runs) < n_lanes and runs:
        s, e = runs[0][0], runs[-1][1]
        step = (e - s) / n_lanes
        runs = [[int(s + k * step), int(s + (k + 1) * step)] for k in range(n_lanes)]
    return runs


def band_center_y(ecl, x0, x1, y0, y1):
    p = ecl[y0:y1, x0:x1].mean(axis=1)
    bg = np.median(p)
    w = np.clip(bg - p, 0, None)
    if w.sum() == 0:
        return None
    ys = np.arange(y0, y1)
    return round(float((ys * w).sum() / w.sum()), 1)


def saturation_frac(ecl, box, level=5):
    x0, x1, y0, y1 = box
    reg = ecl[y0:y1, x0:x1]
    return round(float((reg < level).mean()), 4)


def render_overlay(path, out, marker_mem=None, ladder=None, lanes=None, bands=None):
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    if marker_mem:
        y0, y1 = marker_mem
        d.rectangle([0, y0, im.width - 1, y1], outline=(255, 80, 0), width=3)
    if ladder:
        x0, x1 = ladder["x_window"]
        d.rectangle([x0, marker_mem[0], x1, marker_mem[1]], outline=(0, 160, 255), width=3)
        for c, _, _, _ in ladder["dips"]:
            d.line([(x0, c), (x1, c)], fill=(0, 200, 255), width=2)
            d.text((x1 + 6, c - 8), f"{c:.0f}", fill=(0, 160, 255))
    if lanes:
        for k, (x0, x1) in enumerate(lanes):
            d.rectangle([x0, bands["y_range"][0] if bands else 0, x1,
                         bands["y_range"][1] if bands else im.height - 1],
                        outline=(0, 200, 0), width=2)
            d.text((x0 + 2, 20), f"L{k+1}", fill=(0, 160, 0))
    if bands and bands.get("centers"):
        for (x0, x1), cy in zip(lanes, bands["centers"]):
            if cy is None:
                continue
            d.line([(x0, cy), (x1, cy)], fill=(255, 0, 0), width=2)
            d.text((x1 + 6, cy - 8), f"{cy:.0f}", fill=(255, 0, 0))
    im.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ecl", required=True)
    ap.add_argument("--marker")
    ap.add_argument("--merge")
    ap.add_argument("--ladder", default="180,135,100,75,65,45,35,25,15,10")
    ap.add_argument("--anchor", action="append", default=[])
    ap.add_argument("--lanes", type=int, default=None)
    ap.add_argument("--band-y", default=None, help="y0,y1 range containing bands (ECL)")
    ap.add_argument("--ladder-x", default=None, help="x0,x1 of ladder lane (marker)")
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--out", default="blot_map.json")
    ap.add_argument("--overlay", default=None)
    args = ap.parse_args()

    ecl = load_gray(args.ecl, args.invert)
    H, W = ecl.shape
    result = {"ecl": {"file": args.ecl, "size": [W, H]}}

    # band y-range: auto-guess if absent (middle 60% of height)
    if args.band_y:
        band_y = tuple(int(v) for v in args.band_y.split(","))
    else:
        band_y = (int(H * 0.35), int(H * 0.75))
    result["ecl"]["band_y_range"] = list(band_y)

    runs = detect_lanes(ecl, band_y, n_lanes=args.lanes)
    if args.lanes and len(runs) > args.lanes:
        runs = sorted(sorted(runs, key=lambda r: r[0] - r[1])[:args.lanes])
    centers = [band_center_y(ecl, x0, x1, band_y[0], band_y[1]) for x0, x1 in runs]
    depths, sats = [], []
    for x0, x1 in runs:
        p = ecl[band_y[0]:band_y[1], x0:x1].mean(axis=1)
        depths.append(round(float(np.median(p) - p.min()), 1))
        sats.append(saturation_frac(ecl, (x0, x1, band_y[0], band_y[1])))
    result["ecl"]["lanes"] = [
        {"lane": k + 1, "x_run": [int(a), int(b)], "band_y": centers[k],
         "band_depth": depths[k], "sat_frac": sats[k]}
        for k, (a, b) in enumerate(runs)]

    if args.marker:
        marker = load_gray(args.marker)
        mem = membrane_extent(marker)
        result["marker"] = {"file": args.marker, "membrane_y": list(mem) if mem else None}
        if mem:
            lx = tuple(int(v) for v in args.ladder_x.split(",")) if args.ladder_x else None
            lad = ladder_bands(marker, mem, lx)
            result["marker"].update(lad)
    if args.merge:
        # fallback/confirmation: merge composites often show faint ladder bands the
        # overexposed marker channel misses
        merge = load_gray(args.merge)
        mem = membrane_extent(merge)
        if mem:
            lx = tuple(int(v) for v in args.ladder_x.split(",")) if args.ladder_x else None
            lad = ladder_bands(merge, mem, lx)
            lad["membrane_y"] = list(mem)
            result["merge_ladder"] = lad

    # ladder assignment: try every provided ladder source; rank candidates by
    # anchor agreement with observed ECL bands, then RMSE
    ladder = [float(v) for v in args.ladder.split(",")]
    anchors = {}
    for a in args.anchor:
        name, mw = a.split("=")
        anchors[name] = float(mw)
    ecl_band_ys = [c for c in centers if c is not None]
    mem_y = None
    for key in ("marker", "merge_ladder"):
        if key in result and result[key].get("membrane_y"):
            mem_y = result[key]["membrane_y"]
            break
    sources = {}
    for key in ("marker", "merge_ladder"):
        if key in result and result[key].get("dips"):
            obs = [d[0] for d in result[key]["dips"]]
            cands = assign_ladder(obs, ladder, mem_y=mem_y, anchors=anchors,
                                  ecl_band_ys=ecl_band_ys)
            if cands:
                sources[key] = {"n_dips": len(obs), "best": cands[0], "candidates": cands[:5]}
    if sources:
        best_src = min(sources, key=lambda k: (sources[k]["best"].get("anchor_band_dist_px", 0),
                                               sources[k]["best"]["rmse"]))
        result["ladder_assignment"] = {
            "source": best_src,
            "n_dips": sources[best_src]["n_dips"],
            "best": sources[best_src]["best"],
            "all_sources": {k: v["best"] for k, v in sources.items()},
        }

    # anchors: predicted y for expected MW using best assignment
    if args.anchor and result.get("ladder_assignment"):
        best = result["ladder_assignment"]["best"]
        result["anchors"] = {
            a.split("=")[0]: {"expected_mw": float(a.split("=")[1]),
                              "predicted_y": best["anchor_pred"][a.split("=")[0]]}
            for a in args.anchor
        }
        result["anchors_note"] = ("predicted_y should sit on the observed band of the lane "
                                  "containing this protein (see ecl.lanes[].band_y).")

    if args.overlay:
        render_overlay(args.ecl, args.overlay,
                       marker_mem=result.get("marker", {}).get("membrane_y"),
                       ladder={"x_window": result["marker"]["x_window"],
                               "dips": result["marker"]["dips"]} if args.marker and mem else None,
                       lanes=runs, bands={"centers": centers, "y_range": list(band_y)})

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
