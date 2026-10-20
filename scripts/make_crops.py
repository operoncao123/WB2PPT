#!/usr/bin/env python3
"""Crop a blot panel from a raw ECL scan with contrast normalization.

Usage:
  python3 make_crops.py --src PATH --box x0,y0,x1,y1 --out out.png \
      [--scale 2] [--stretch 1.5,99.7] [--invert]

- box is in native scan pixels (x0,y0,x1,y1).
- Percentile contrast stretch defaults to 1.5-99.7.
- Output is upscaled 2x (LANCZOS) for crisp display in PPT/HTML.
"""

import argparse

import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True)
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1 native pixels")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--stretch", default="1.5,99.7")
    ap.add_argument("--invert", action="store_true", help="source is white-bands-on-black")
    args = ap.parse_args()

    im = Image.open(args.src).convert("L")
    if args.invert:
        a0 = 255.0 - np.array(im, dtype=float)
        im = Image.fromarray(a0.astype(np.uint8))
    c = im.crop(tuple(int(v) for v in args.box.split(",")))
    a = np.array(c, dtype=float)
    lo_p, hi_p = (float(v) for v in args.stretch.split(","))
    lo, hi = np.percentile(a, [lo_p, hi_p])
    a = np.clip((a - lo) / (hi - lo) * 255, 0, 255)
    img = Image.fromarray(a.astype(np.uint8)).resize(
        (c.width * args.scale, c.height * args.scale), Image.LANCZOS)
    img.save(args.out)
    print(f"{args.out} {img.size} (from box {args.box}, stretch {lo:.1f}-{hi:.1f})")


if __name__ == "__main__":
    main()
