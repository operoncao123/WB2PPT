#!/usr/bin/env bash
# Render a PPTX to PNGs for visual QA.
# Usage: qa_render.sh <deck.pptx> <outdir> [dpi]
set -euo pipefail

PPTX="$1"
OUT="$2"
DPI="${3:-110}"

mkdir -p "$OUT"
soffice --headless --convert-to pdf "$PPTX" --outdir "$OUT" >/dev/null 2>&1
PDF="$OUT/$(basename "${PPTX%.pptx}").pdf"

python3 - "$PDF" "$OUT" "$DPI" <<'EOF'
import sys
import fitz  # PyMuPDF

pdf, out, dpi = sys.argv[1], sys.argv[2], int(sys.argv[3])
doc = fitz.open(pdf)
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=dpi)
    pix.save(f"{out}/slide-{i + 1}.png")
    print(f"saved {out}/slide-{i + 1}.png ({pix.width}x{pix.height})")
EOF
