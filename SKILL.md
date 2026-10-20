---
name: raw-western-blot-to-ppt
description: Build a lab-meeting PPT (plus HTML preview) from raw Western blot imager exports. Analyzes multi-exposure ECL scans and marker channels, detects lanes and bands, assigns ladder molecular weights by semi-log consistency, levels tilted band rows by measured-angle rotation before cropping, crops contrast-normalized panels, and generates an editable PPTX with MW labels, rotated lane sample names, an antibody info block, inheriting the format of a user-provided demo PPT. Use when the user asks to 整理WB数据 / 整理Western Blot数据到PPT / 做WB结果PPT / organize Western blot images into PowerPoint.
---

# Raw Western Blot → PPT

Turn a folder of raw imager exports into a polished, **editable** WB slide. Typical input: one
folder per antibody containing `<id>_<antibody>_<variant>.Tif` files, e.g.
`IM000001_anti-Cas9_super_long.Tif`, plus `IM000002_anti-Cas9_marker.Tif` (membrane/ladder
photo) and `IM000003_anti-Cas9_long_merge.Tif` (composite).

Golden rule learned from real iterations: **the hard part is reading the images, not the
layout.** Do the analysis honestly, show evidence to the user, ask one consolidated round of
questions, then build. Never eyeball molecular-weight label positions — compute them from the
blot map.

## Phase 0 — Inventory

1. `find` image files (`.Tif/.tif/.png/.jpg`); group by antibody (the filename token before the
   last variant token; the imager scan ID prefix groups files from the same capture).
2. Classify variants by suffix:
   - `marker` — membrane photo: bright membrane on dark background, shows the ladder. May be
     overexposed (membrane saturated, ladder bands faint gray).
   - exposure series (`short`, `long`, `super_long`, `short_long`, …) — ECL signal channels:
     dark bands on white background. These are the screenshot sources.
   - anything ending in `merge` — composite of marker + ECL. **NEVER crop screenshots from
     merges** (user requirement in most labs: screenshots must come from un-merged data).
     Merges ARE useful as a fallback for reading faint ladder bands.
3. Note display polarity: some exports are white-bands-on-black. Normalize to
   dark-bands-on-white (invert) before analysis/presentation.
4. **Dedup check**: pixel-compare each "main" ECL file against its own `_marker` file
   (`np.abs(np.asarray(a,int) - np.asarray(b,int)).mean()`). A mis-export can put the
   membrane photo under the main name — real case: gel-1 Cas9 "long" slot was
   pixel-identical to the marker (mean|diff| = 0), no ECL signal at all; only the
   `short` file was usable. Note the substitution on the slide.

## Phase 1 — Analyze (`scripts/analyze_scan.py`)

Run per antibody on the best-guess exposure + marker channel:

```bash
python3 scripts/analyze_scan.py \
  --ecl anti-Cas9/IM000001_anti-Cas9_super_long.Tif \
  --marker anti-Cas9/IM000002_anti-Cas9_marker.Tif \
  --ladder 180,135,100,75,65,45,35,25,15,10 \
  --anchor "Cas9=160" --anchor "Actin=42" \
  --lanes 4 --out blot_map_cas9.json --overlay overlay_cas9.png
```

The analyzer detects: membrane vertical extent, ladder dips (marker channel), lane x-runs,
per-lane band y-centers (ECL), saturation, and proposes ladder assignments.

**User's standard marker (explicitly confirmed 20261018):** 180, 135, 100, 75, 65, 45, 35, 25,
15, 10 kD — the same list as the `--ladder` default above; see `references/marker.md`.
**MW labels must be calibrated from marker rung positions — NEVER estimated from construct-size
arithmetic** (real case: Protein X-3×FLAG bands were labeled ~32/~24 kD from arithmetic; the user
rejected this — "根据marker的位置来标条带大小").

**Annotation scheme = the USER's rung values at rung positions, not the agent's band-size
estimates.** The user annotates the figure with the ladder rungs their strips show (real case:
45 kD on the actin strip just above the actin band; 35/25 kD on the FLAG strip) and expects
those exact plain numbers ("35"/"25"/"45", no tilde) on ticks at those positions. When the
user corrects your calibrated numbers, adopt them verbatim and drop any contradicting
"please verify" notes — do not argue from the pixel calibration. If a rung's identity is
genuinely ambiguous, ask once; do not ship a guess.

**Calibrating a cut strip whose ladder is partially visible.** With ≥3 rungs: enumerate
consecutive slices of the marker list; keep only fits where ONE px/decade scale explains every
gap (per-gap px/Δlog within ~15%); cross-validate against a known anchor (actin = 42) or the
companion strip's cut position (two strips cut from one gel share the cut MW — matched to ~1 kD
in the real case). Report the ECL-vs-marker registration uncertainty (±10–20px occurred on one
real scan) and round labels with "~". If only 2 rungs are visible, the assignment is usually
unresolvable — say so rather than guessing.

**Ladder assignment rule (the #1 error risk).** Each membrane strip shows only a WINDOW of the
ladder. Enumerate consecutive slices of the user's ladder list against the observed dip
y-positions; fit `y = a + b·log10(MW)`; accept only `b > 0` (y grows downward as MW shrinks);
rank by RMSE. Then anchor-verify with known protein sizes from the user (e.g. Actin = 42 must
land between the 45 and 35 dips). **Always** render the overlay PNG and show it to the user for
confirmation before building anything. If the marker channel is overexposed and dips are
missing, retry with the merge channel or a contrast stretch before giving up.

**Ladder on cut membrane pieces.** When the membrane was cut (e.g. above Actin), the top
piece's marker photo often shows "dips" whose spacing fits NO consecutive slice of the
ladder list — they are well-line/shadow artifacts, not ladder bands. Do not calibrate MW
from them. On the bottom piece, validate the ladder window through the protein anchor
(Actin = 42 landing between the 45 and 35 dips). For editor-sized targets on top pieces,
label the MW from the known construct size and flag the value for user confirmation.

**Exposure recommendation.** Prefer the shortest exposure where every target band is well above
noise (band depth ≥ ~30 gray levels) and saturation is minimal (saturation fraction < ~5%,
i.e. no large flat-black cores). Present the recommendation plus one alternative per antibody.

**Lanes.** Detect dark x-runs inside the band y-range. If adjacent lanes merge into one run,
split with per-lane windows read off a zoomed crop. Record lane centers as **fractions of panel
width** — membrane strips are placed on the imager tray independently, so absolute coordinates
never carry across scans. Use the fractions to align panels when cropping.

Ignore small round dark blobs (dust/air bubbles) when calling bands. Membrane top/bottom edges
produce false dips — exclude ~15px from membrane ends. Smear below a band is real signal
(degradation), but the user may still want it cropped away — ask.

**Lane-grid QC (cross-panel; the #2 error risk — bit a real deck, fixed 20261012).**
`analyze_scan.py --lanes N` fills a shortfall of detected x-runs by evenly splitting the
detected span into N windows. If weak lanes fall below the detection threshold, the detected
span UNDER-COVERS the true grid and the split windows drift — by the right edge they can be
>1 lane off, the outer lanes fall outside the span and get cropped away, and every per-lane
number sampled in those windows (band y, depth → clone calls) is mis-assigned. Real damage:
a Cas9 panel lost clone 13 entirely, misaligned with its Actin panel, and clone 9 (strong)
was reported as trace while 12/13 (weak) looked moderate.

Before trusting any lane windows, cross-check the panels of the SAME gel against each other:

1. Ground truth = the same gel's other-antibody panel (the clean band rows, usually Actin).
   Same gel → same lane count, same spacing (membrane pieces are same-scale; the pieces sit
   at different tray offsets only).
2. Sweep detection thresholds (e.g. 6 → 2.5 gray levels) on both panels. If the detected
   span is shorter than (N−1)·spacing, or a gap ≥ 2 spacings exists between runs, weak
   lanes are hidden inside — the naive windows are WRONG.
3. Fit `x_target = a·x_ref + b` from confidently detected columns; healthy fit:
   a ∈ [0.97, 1.03], RMSE ≤ ~5px. Beware the ambiguity trap: two near-uniform grids can
   match "shifted by k lanes" with a similar inlier count — initialize the offset by
   voting on detected-to-detected position differences, never by median-to-median alone
   (`scripts/check_lane_grid.py` implements all of this).
4. Predict ALL N centers from the fitted grid (silent weak lanes included), re-crop the
   target panel from lane-1 left edge to lane-N right edge + ~20px so stacked panels align,
   recompute `lane_fracs`, and **re-sample band y/depths only at the corrected windows** —
   conclusions written from pre-fix windows must be re-derived.
5. Show the corrected overlay to the user. Non-lane column signals exist: on cut top pieces,
   the well line collects a row of high-MW blobs just below the membrane top, at ALL x
   including beyond the last lane — those columns are NOT lanes (the bottom piece's clean
   actin rows prove it). Crop them out and say so.

```bash
python3 scripts/check_lane_grid.py \
  --ref-ecl anti-actin.Tif --ref-band-y 1030,1130 \
  --ecl anti-Cas9_short.Tif --band-y 1040,1300 \
  --n-lanes 13 --crop-y 1040,1295 --out grid_check.json
# -> fitted x_t = a*x_r + b (rmse), predicted N centers, crop_box, lane_fracs, warnings
# exit 1 = verify manually before building (uneven spacing / scale anomaly / drift risk)
```

## Phase 2 — ONE consolidated question round

Front-load everything that was unknowable from the images. Ask once, in a single message:

1. Lane sample names in order (or "none").
2. Confirm the ladder assignment (show the overlay image).
3. Confirm exposure choice per antibody.
4. Which bands are target vs non-specific — the MW label goes at the TARGET band height; the
   user may want non-specific regions cropped out entirely (this happened: FLAG panel kept only
   the lane-4 band region).
5. Antibody info per blot: brand, catalog #, dilution, **direct-HRP vs secondary** (never
   assume the secondary — ask; in one real case two of three antibodies were HRP-direct).
6. Unit spelling (`kD` vs `kDa`) — follow the user even if nonstandard.
7. Demo PPT path, if format inheritance is wanted.
8. Layout preferences: crop tightness (vertical AND horizontal are separate asks — users mean
   different things by "too wide"), image scale, panel gap, border width, minimum font size.

Write everything to `spec.yaml` (schema in `build_deck.py` header / below). Later revisions
edit the spec and re-run — do not redo analysis.

## Phase 3 — Crops (`scripts/level_bands.py`, then `scripts/make_crops.py`)

- **Level the bands first (standing user requirement since 20261018):** every band row must be
  horizontal in the presented panel — raw scans are usually tilted a few degrees and the user
  will ask for it. Measure per-lane band y-centers, fit the least-squares line per row, rotate
  the RAW ECL scan by that angle (`scripts/level_bands.py`), save the rotated full image to
  `out/rotated/` (provenance — the crops derive from it), and **re-derive everything from the
  rotated image**: lane centers, band y-centers / `tick_frac`, crop boxes, panel aspect. Then
  disclose the rotation in the info block, e.g.
  `"Panels rotated to level the bands (FLAG -4.4°, actin -2.5°)"` — raw-data records must note
  digital processing. Rows within one panel can have DIFFERENT tilts (gel distortion, not a
  rigid tilt; real case: precursor −5.2° vs mature −3.7°): rotate by the mean angle, expect
  ±1° residuals across the panel, and say so — don't warp per-row without asking.

```bash
python3 scripts/level_bands.py --src RAW_ECL.Tif --out out/rotated/panel_rot.tif \
  --row "1055,1110:862,959,1056,1153" --row "1240,1300:862,959,1056,1153" \
  --json out/rotated/panel_level.json
# -> applied angle, per-row before/after slopes + residual rise in px; exit 1 = sign/window error
```

- Source: **non-merged ECL channels only**.
- Vertical bounds: band top − ~15px to signal bottom + ~15px (drop empty membrane; users ask
  for this repeatedly and separately for width and height — treat them as independent knobs).
- Horizontal: lane span + ~20px margins. Give all panels of a stack the SAME native pixel width
  and the same lane-center fractions so lanes align vertically across panels.
- Percentile contrast stretch (default 1.5–99.7), grayscale, 2× LANCZOS upscale. Save to
  `screenshots/` — these files are deliverables, not just intermediates.

## Phase 4 — Build (`scripts/build_deck.py`)

Render `spec.yaml` → native PPTX + HTML preview with **identical geometry** (both derive from
the same spec; 1 inch = 96 px in HTML).

If a demo PPT is given, parse it first (python-pptx): slide size, fonts, and the element
arrangement (e.g. Aim/Conditions/Conclusion text block top-left, MW label + tick line left of
each blot, antibody name right, Exp. Date bottom-right). Inherit that visual language rather
than inventing one.

**Panels with TWO target bands** (precursor + mature): the spec supports one `mw` per blot;
add the second label + tick by post-patching the PPTX (and the HTML, to keep geometry in
sync) with identical conventions — label box at `blot_x − 1.0`, w 0.82, right-aligned Arial
`label_size`; tick rectangle at `blot_x − 0.14`, w 0.10, h 0.015. Post-patch shapes MUST get
the same shadow treatment as build_deck (below), or the second tick ships with a shadow.

**Public demo / de-identified decks**: never reuse real scan crops — generate synthetic
phantom "scans" instead (white 2160×2160 canvas, dark 2-D Gaussian bands per lane + Gaussian
noise + slight blur, run through the same make_crops pipeline), swap in Protein X / Mut-A/B/C
style names, placeholder antibody lines, and a visible "Demo deck: synthetic phantom scans"
line. Verified on the 20261018 demo deck.

Layout system defaults (all overridable in spec):

- Header block top-left: Title (bold), `Aim:`, `Experimental Conditions:`, `Conclusion:` —
  real text boxes, Arial, explicit font name on every run.
- Figure cluster **adjacent to the text block** — no large vertical void above it. Per blot
  row, left to right: MW label (right-aligned, `"<value> <unit>"`) + short tick line → panel
  image with border → antibody name.
- Panels stacked with a SMALL gap (~0.06 in), like a multi-panel figure.
- Sample names rotated −45° (python-pptx `rotation=315`, HTML `rotate(-45deg)` with
  `transform-origin:left bottom`), above the **FIRST blot only** (same gel → same samples),
  one per lane, starting just outside the image edge at the lane center — never overlapping.
- Info block bottom-right: per antibody `brand #catalog, dilution;` + second Ab line (or
  "direct HRP, no 2nd Ab"), plus Exp. Date. Minimum 11pt — this text is read at the bench.
- Panel borders default 0.5pt black (`picture.line`), thin.

## Phase 5 — QA + deliver

1. `scripts/qa_render.sh <pptx> <outdir>` → slide PNG(s) via LibreOffice + PyMuPDF.
2. Programmatic geometry check: nothing outside the slide, no text/image overlaps.
   **Info-block bottom overflow is the one that bites** — build_deck renders 0.20in per line,
   so check `info.y + 0.20·len(lines) + 0.1 ≤ slide height` before rendering. Adding one
   disclosure line (e.g. the rotation note) turned a 8-line block at y=5.95 into a clipped
   9th line on a 7.5in slide (real case, caught by the judge).
2b. **Lane-count + alignment check on the render**: every panel shows exactly
    `len(samples)` lanes; stacked panels of the same gel have their first/last lane centers
    within ~0.1 lane-spacing of each other at the same display width, and each rotated
    sample label sits on its own lane's band column. This is the check that catches
    grid-drift (the user sees it as "one lane missing at the right / panels don't line up")
    — a generic layout judge will pass it, so do it yourself on the PNG.
3. Dispatch the judge subagent on the render with the user's requirement list. Fix and re-render
   until pass.
4. Deliver: PPTX + HTML + `screenshots/` + a short summary **listing assumptions** (ladder
   assignment, exposure choices, secondary-antibody assumptions, cropped-out regions).

## spec.yaml schema (build_deck.py)

```yaml
slide: {w: 13.333, h: 7.5}
font: Arial
unit: kD                    # appended to mw labels
title: "..."
aim: "..."
conditions: ["...", "..."]  # rendered as bullet lines
conclusion: ["...", "..."]
samples: [ABE, CBE, PE, SpCas9]   # labels above the FIRST blot; omit key if none
lane_fracs: [0.1875, 0.396, 0.615, 0.823]
label_size: 12              # MW / sample / antibody text
blots:
  - image: screenshots/anti-Cas9_super_long.png
    mw: "160"               # text; unit auto-appended
    tick_frac: 0.457        # band-height fraction of panel height
    right_label: anti-Cas9
    h: 0.9007               # inches; w comes from layout.blot_w
  - { image: ..., mw: "160", tick_frac: 0.376, right_label: anti-FLAG, h: 0.5889 }
layout:
  blot_x: 3.50              # left edge of panels
  blot_w: 3.048
  y0: 2.95                  # top of first panel
  gap: 0.06
  border_pt: 0.5
info:                       # bottom-right block
  x: 8.40
  y: 5.95
  w: 4.60
  size: 11
  lines:
    - "anti-Cas9: CST #14697 (7A9-3A3), 1:1,000;"
    - "  2nd Ab: anti-mouse IgG-HRP"
    - "anti-FLAG: Sigma #F3165 (HRP-M2), 1:10,000;"
    - "  no 2nd Ab (direct HRP)"
    - "Exp. Date: 20260827"
```

## Common pitfalls (each one caused a real revision)

- Cropping from `merge` files instead of raw ECL channels.
- Assuming the user's "too wide" means horizontal — clarify vertical vs horizontal margins.
- Repeating lane sample names under every panel (label once, on the top panel).
- Eyeballing MW label heights — always derive from the blot map (`tick_frac`).
- Marking a non-specific band's height as the target MW (ask which bands are real).
- Hardcoding secondary antibodies — FLAG M2-HRP and many Actin antibodies are HRP-direct.
- Leaving 1.5pt borders / 9pt info text when the user wants thin borders and larger notes.
- Absolute pixel coordinates carried across different membrane-strip scans.
- Long empty membrane margins left in crops (users want tight panels; iterate on the spec).
- **Trusting `--lanes N` even-split windows when weak lanes dropped below the detection
  threshold** — the detected span under-covers the grid, windows drift up to >1 lane by the
  right edge, and outer lanes get cropped away (real case: Cas9 panel shipped missing clone
  13 and misaligned with Actin; caught by the user, not by the judge).
- **Sampling per-lane band stats at drifting windows and writing conclusions from them** —
  clone calls came out wrong (strong clone 9 reported as trace) even though each individual
  depth number looked plausible. Re-derive every per-clone call after the grid QC.
- Using an ECL export that is a pixel-identical duplicate of the marker photo (dedup-check
  in Phase 0; the "long" slot may contain no signal at all).
- Calibrating MW from ladder dips on a cut membrane top-piece — pseudo-dips there fit no
  ladder slice; label editor MWs from construct sizes and confirm with the user.
- Cropping a panel to its detected-signal span instead of the full lane grid — panels of the
  same gel must keep first/last lanes aligned even when the end lanes are empty.
- **Rotating with the wrong sign** — PIL `rotate(angle)` positive is counterclockwise (visual);
  negating the row's measured angle doubles the tilt instead of leveling it (real case: bands
  went from −5.2° to −9.0° before the error was caught by re-measurement). Pass
  `degrees(atan(slope))` directly as the rotate angle and always verify by re-measuring the
  rotated image (`level_bands.py` does both).
- **Re-segmenting lanes on the rotated image** — bicubic resampling raises the between-lane
  valleys, so run-detection tuned pre-rotation glues all lanes into one run. Transform the
  pre-rotation lane grid analytically (rotation about the image center is rigid — spacing is
  preserved) and refine in small local windows instead.
- **Treating one panel's band rows as parallel** — precursor and mature rows can differ by
  ~1.5° (gel distortion); no rigid rotation levels both. Rotate by the mean angle, disclose
  the residual, and only per-row warping would do better (don't warp raw data without asking).
- **Adding the rotation-disclosure line without checking the info-block bottom** — the 9th
  line at y=5.95 on a 7.5in slide clipped mid-glyph (caught by the judge). Move the block up
  or merge lines; see the Phase 5 overflow check.
- **Estimating MW from construct size instead of calibrating against the marker** — the user
  explicitly rejected arithmetic labels ("marker不是你随便标的"): Protein X-3×FLAG bands had been
  labeled ~32/~24 kD from protein arithmetic. Calibrate from rungs — and then confirm the
  annotation scheme with the user.
- **Substituting your own calibrated band sizes for the user's rung annotations** — after the
  user says the ticks are 45 (actin strip) / 35 and 25 (FLAG strip) at rung positions, ship
  exactly those plain numbers; don't relabel with pixel-calibrated values (~29/~11) or keep a
  contradicting "verify" note. Two more practical notes from the same case: actin strips crop
  tight above the band — leave generous membrane above it (user: "尤其是上方"); and crop
  asymmetrically (wide top) rather than centering on the band.
- **Editing spec.yaml via Python `str.replace` with unicode escapes** — the file holds literal
  UTF-8 (β, ×, °); `\\u03b2`-style patterns silently fail to match and the stale text ships.
  Use literal strings and re-parse the YAML afterwards to verify the edit landed.
- **Shadow under the MW tick lines** — python-pptx `add_shape` emits `<p:style>` whose
  `effectRef idx="2"` points at the theme shadow; WPS/LibreOffice render it even after
  `shape.shadow.inherit = False` (empty `<a:effectLst/>` is not enough). The user spotted the
  shading on the very first delivery of the tick design. Fix (in build_deck, and in ANY
  post-patch that adds shapes): delete the `<p:style>` element from the shape AND set
  `shadow.inherit = False`. Verify on a 300-dpi render zoomed on a tick, not at slide scale.
