# User's standard Western blot marker

- **Ladder rungs: 180, 135, 100, 75, 65, 45, 35, 25, 15, 10 kD** (semi-log).
- Confirmed by the user 20261018 ("skills 里面有我常用的 marker 条带"); the same list is the
  `--ladder` default in SKILL.md Phase 1. If the user ever names a different marker, update
  both places.

## Rules

1. **MW labels always come from marker rung positions** (semi-log fit `y = a − P·log10(MW)`),
   never from construct-size arithmetic. A tag adds ~2.4 kD in theory but SDS migration can
   differ by several kD — arithmetic labels were explicitly rejected by the user.
2. **Cut strip with partially visible ladder**: enumerate consecutive slices of the rung list;
   keep slices where one px/decade scale explains every gap (per-gap px/Δlog within ~15%);
   cross-validate with a known anchor (actin = 42) and/or the companion strip's cut position
   (two strips cut from one gel must agree on the cut MW; matched to ~1 kD in the real case).
3. **Registration caveat**: the ECL capture and the white-light marker capture may be offset
   by 10–20px on a given scan; propagate that as ±0.5–1.5 kD uncertainty and round labels
   with "~". Check registration by comparing the membrane edge visible in both images.
4. **Contradictions with expected biology go to the user**: if the calibrated size of a band
   the user calls "mature" lands far from the expected size, keep the calibrated number on the
   slide, add a "please verify" note, and raise it in the delivery summary.

## Real case (20261018, Protein X-3×FLAG overexpression in a mammalian cell line)

- Actin strip (top piece): 6 dark bands in the ladder column, of which the 5-rung window
  [180,135,100,75,65] fit with the actin = 42 anchor landing within 1px; the 6th band was
  unexplained by the rung list (a doublet/shadow — do not force it).
- FLAG strip (bottom piece): 4 visible rungs, best-fit slice [35,25,15,10] (433 px/decade).
- The user then specified the final annotation scheme directly: **"35 kD" and "25 kD" ticks at
  the FLAG strip's two rungs/bands, "45 kD" just above the actin band on the actin strip** —
  plain numbers, no tilde, no "please verify" notes. The user's asserted rung values override
  the agent's calibration; the deliverable ships their scheme verbatim.
- Cropping note: the actin panel was too tight above the band — leave generous membrane headroom
  above the band (user: "尤其是上方的位置…保留一个特定的距离").
