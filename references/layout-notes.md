# Layout notes (hard-won values from a real 8-iteration session)

These are starting defaults that satisfied a working lab user; put them in the spec and let
the user adjust, but do not silently regress them between versions.

## Panel crops
- Tight vertical bounds: band top − ~15px to signal bottom + ~15px. "Cut empty membrane" was
  asked for THREE times (once for width, twice for height) — treat vertical and horizontal
  tightness as independent requirements and confirm both.
- Horizontal: lane span + ~20px per side. Same native pixel width for every panel in a stack.
- Percentile stretch 1.5–99.7; 2× LANCZOS upscale keeps bands crisp at panel widths of 3–5in.

## Figure block placement
- Place the figure cluster directly below the text block (gap to rotated sample names
  ≈ 0.4–0.5in). A >1in void above the figure was flagged as "layout problem".
- Center the cluster horizontally-ish on the slide (blot_x ≈ 3.5 on a 13.33in slide when
  panels are ~3in wide); leaving it flush-left with the text made the right side look empty.

## Panel stack
- Vertical gap between panels: 0.06in (user: "不同的信号之间隔的距离其实很小").
- Thin black border on every panel: 0.5pt (user explicitly downgraded 1.5pt → 0.5pt).
- Panel width ~70% of an initial full-width layout was requested when panels were 4.75in on a
  13.33in slide — i.e. panels ≈ 3.0–3.4in wide look right for 4 lanes.

## Labels
- MW label format: "<value> <unit>" right-aligned + 0.10in tick line at the band height.
  Unit goes IN the label ("160 kD"), tick y = blot_y + tick_frac × panel_h.
- MW label height = TARGET band height from the blot map, not the panel center. If only one
  lane's band is real (e.g. tagged control in lane 4), anchor the label to that lane's band.
- Sample names: rotated −45°, above the FIRST panel only, one per lane, text start ≈ lane
  center, fully outside the image. Never repeat them on lower panels (same gel, same samples).
- Antibody name vertically centered on its panel, ~0.15in right of the panel edge.

## Text
- Info block bottom-right ≥11pt (9pt was rejected as too small; "至少加大两个" = +2pt).
- Unit spelling follows the user ("kD"), even if "kDa" is the standard form.
- All text native/editable; never bake labels into the images.
- CJK vendor names (华新博创) render fine if the font name is Arial + system CJK fallback.

## Process
- Front-load questions into ONE round (samples, target bands, antibody catalogs/secondaries,
  unit, demo PPT, layout prefs). Eight delivery iterations on the same slide is the failure
  mode this skill exists to prevent.
- Show the ladder-assignment overlay before building; MW annotation errors destroy trust.
- Render → judge → fix loop is cheap; always run it before delivering.
