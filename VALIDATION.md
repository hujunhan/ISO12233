# Validation

Validated locally on macOS with the dependency versions in requirements.txt.

## Geometry

- All 20 components, 1,154 painted shapes, 159 labels and paint styles checked.
- Source line endpoints and cubic control points were compared independently
  against the generated drawsvg primitives after applying their placements.
- Maximum coordinate error: **9.095e-13 pt**, below the **0.005 pt** criterion.
- Original SVG contains 1,156 paths; two have no fill or stroke and are
  Illustrator layout boxes. They are omitted, along with footer labels.
- Original waveform contours, line widths, bar spacing, source asymmetries and
  colors are retained. Label baselines, sizes and contents are measured;
  Liberation Sans glyphs are intentionally substituted and not claimed equal.
- SVG dimensions explicitly use points, so print dimensions do not depend on
  a browser's 96 CSS pixels/inch interpretation.

## Raster comparison

Reference and generated geometry were rasterized with PyMuPDF, with 2x
sampling and Lanczos reduction. Both comparisons exclude labels, but include
all testing patterns. Values below are differences on the 0-255 channel scale,
not differences in simulated RAW DN.

| Width x height | Mean absolute difference | Maximum difference | Pixels with any changed channel |
|---|---:|---:|---:|
| 2048 x 1243 | 0.0009021 | 8 | 974 / 2,545,664 |
| 8192 x 4970 | 0.0007962 | 9 | 12,475 / 40,714,240 |

Equivalent path representations yield tiny raster-edge differences despite
matching vector coordinates. Raster acceptance is mean absolute error <=1
on the 8-bit channel scale, together with the much tighter vector-coordinate
criterion. No bit-identical raster claim is made.

The full preview and six paired detail crops were visually inspected: center
zone plate, vertical high-frequency wedge, bottom square-wave sweeps, two
corner crossings, and the diagonal sweep. No missing stripes, clipping or
overlapping test patterns was observed. Original high-frequency aliasing at
limited raster resolution is retained rather than retouched.

## PDF cross-check

The existing PDF outer frame establishes translation `(6.29297018, 6.91356993)`
pt to SVG coordinates. All 20 component layers match and their painted shape
counts agree. Bidirectional nearest vertex/control-point distances are below
0.006042 pt. The largest differences are:

- Corner low-frequency wedges: 0.005318 pt.
- High-frequency wedges: 0.006042 pt.

This measurement is a vertex/control-point comparison, not Hausdorff contour
distance. The PDF and SVG use slightly different numerical coordinates;
the PDF also uses CMYK colors with different rendered dark values. SVG is
the authoritative reconstruction reference. Neither document establishes ISO
compliance or authorizes a blanket open-source license for the artwork.

## Tests and outputs

Five tests pass: repeatable standalone generation/open-font outlines and
label content; aspect-preserving PNG size; independent reference geometry;
rejection of a deliberately changed bar width; and reproducible measurements.

Local untracked outputs include the SVG, 8192 x 4970 PNG, JSON report,
geometry previews, overlay, amplified difference images and detail comparison
sheet in `output/`. Published example SVG/PNG files are in `charts/`, with a
copy of the machine-readable report in `validation/report.json`. The small
`preview.png` is tracked. Original reference SVG/PDF files remain untracked.
No existing simulation files or RAW dataset were changed.
