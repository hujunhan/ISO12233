# ISO12233:2000 reconstruction

The cropped SVG viewBox is `0 0 1121.273 680.314`, in 1/72-inch points.
The outer frame is approximately 395.56 x 240 mm. The inner white rectangle
is approximately 355.56 x 200 mm. **LW/PH frequency labels refer to the
inner active picture height, not the height of the outer black frame.**
Changing label text alone does not change a pattern's physical frequency.

## What is parameterized

[data/iso2000_measurements.json](../data/iso2000_measurements.json) contains 20 named components, 1,154 painted shapes,
159 labels, and 382 reusable primitives. It stores rectangle widths/heights,
relative polygon vertices, polyline coordinates, and measured cubic/linear
contours, separately from per-instance placement and paint styles. It has no
SVG path strings, font blobs, or embedded reference document.

For example, moving an instance's `origin` moves that shape; changing a
rectangle primitive's `width` modifies every instance sharing that primitive.
To change one instance only, duplicate its primitive and update its index.
All repeated contours share the same renderer. Component IDs preserve the
source names for wedges, sweeps, bars, checkerboard, arrows and zone plate.

### Wedges and sweeps

The continuous square-wave sweeps use **384 straight strokes** (192 in each
direction), plus two compound tick-mark paths. Stroke positions and widths
are measured individually. No spline is used for these sweeps.

Resolution wedges use closed polygon outlines: 52-53 vertices per low-frequency
stripe, and 22 or 62-63 per high-frequency stripe. These counts include both
sides of each stripe. Across the wedge groups there are 136 stripes and 5,391
outline vertices, excluding labels and tick marks. Their smooth appearance
comes from dense line segments and raster antialiasing; the generator does
not fit new splines. The center zone plate also uses measured cubic curves.

This first version deliberately preserves measured contour samples and the
source's small asymmetries. **It does not replace every wedge/sweep with an
ideal analytic frequency formula.** Such a replacement would be a different
chart and would require separate frequency validation. Labels are rendered
as Liberation Sans outlines at their measured baselines/sizes, ensuring
portable appearance. Their glyphs differ from Westin's Myriad/Arial labels.
The printing footer is omitted; source attribution lives in the [README](../README.md),
[NOTICE](../NOTICE) and SVG metadata.

## Re-measure and validate

Run from the repository root. Reference downloads are described in
[references/README.md](../references/README.md).

```bash
python -m iso12233.measure_chart --reference references/ISO_12233-reschart.svg \
  --output data/iso2000_measurements.json
python -m iso12233.validate_chart --output output/validation/iso2000
```

See [geometry and raster validation](iso2000-validation.md) and the
[published report](../reports/iso2000/geometry.json).
