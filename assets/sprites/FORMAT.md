# Sprite format

One character per pixel. Plain text so it diffs, greps and can be hand-edited.

```
# name: THE ARRAY BEAST
# palette: . none  d #0b0908  k #1a1410  b #3b312a  G #f0c14b
........................
..dd................dd..
```

* `# name:` the display name.
* `# palette:` space-separated `CHAR #rrggbb` pairs. `none` = transparent.
* `.` is always transparent, whether or not it is in the palette.
* Every row MUST be the same width. The checker enforces it.
* Canonical size is **24x24** — that renders as 24 columns by 12 terminal rows,
  because one cell holds two vertically stacked pixels (the `▀` half-block).

Check your work with:

    .venv/bin/python tools/sprite_check.py assets/sprites/*.px
