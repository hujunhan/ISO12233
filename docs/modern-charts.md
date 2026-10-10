# Public-reference ISO12233 chart reconstructions

Three modern chart families are implemented. They are **public-reference
reconstructions**, not certified ISO12233:2024 targets. Complete final-standard
verification remains unavailable; the user explicitly chose generation from
public figures, previews and documented parameters.

[data/modern_profiles.json](../data/modern_profiles.json) records documented,
measured/inferred, and selected parameters separately.
[data/modern_references.json](../data/modern_references.json) records URLs,
fingerprints, measurement anchors, and remaining unverified standard details.
The generator runs offline from those profiles and the bundled open font.

## Ready-made outputs

| Chart | Layout and reflectance | SVG | 8192-pixel sRGB PNG | Processing metadata |
|---|---|---|---|---|
| CIPA | 340×240 mm canvas; 300×200 mm active area; five-line 200–2500 LW/PH wedges; selected 60:1 contrast | [SVG](../charts/cipa/chart.svg) | [PNG](../charts/cipa/preview-8192.png) | [JSON](../charts/cipa/metadata.json) |
| e-SFR | Nine four-cycle slanted stars; 5° initial edge; 0.20/0.05 linear reflectance (4:1); sixteen synthetic OECF patches | [SVG](../charts/esfr2024/chart.svg) | [PNG](../charts/esfr2024/preview-8192.png) | [JSON](../charts/esfr2024/metadata.json) |
| s-SFR | Nine 144-cycle sine stars; 0.18 background; selected 0.9/0.009 endpoints (100:1); sixteen linear patches per star | [SVG](../charts/ssfr/chart.svg) | [PNG](../charts/ssfr/preview-8192.png) | [JSON](../charts/ssfr/metadata.json) |

NPY files are local under `output/linear/`, ignored by Git. They are
regenerated using the commands below; no reference documents or photographs are
embedded in the source code. The generated SVG sine images come from formulas.

## Generate

```bash
python -m iso12233.generate_chart --chart cipa --output output/runs/cipa/chart.svg \
  --linear output/runs/cipa/reflectance.npy --png output/runs/cipa/preview.png --width 8192
python -m iso12233.generate_chart --chart esfr2024 --output output/runs/esfr2024/chart.svg \
  --linear output/runs/esfr2024/reflectance.npy --png output/runs/esfr2024/preview.png --width 8192
python -m iso12233.generate_chart --chart ssfr --output output/runs/ssfr/chart.svg \
  --linear output/runs/ssfr/reflectance.npy --png output/runs/ssfr/preview.png --width 8192
```

Each modern invocation writes a metadata JSON, defaulting to the NPY's sibling
or, without an NPY, the SVG's sibling. `--metadata` selects another destination.
`--chart ssfr --ssfr-layout single --cycles 72` produces the single-cell,
lower-cycle alternative. `--supersample 8` increases samples per pixel axis;
4 is the default. The default chart remains the measured Westin 2000 version.

### Simulation input and display output

Use the NPY as spectrally neutral **linear reflectance**, shape `(height,width)`,
dtype float32, row-major. It contains assumed synthetic material reflectances,
not calibrated real print measurements. No exposure, lens blur, noise, CFA or
ISP operation has been applied. Absolute illumination and camera exposure
belong to the simulation stage. Do not apply an inverse gamma to the NPY.

PNG colors are sRGB-encoded for display. SVG gray paint is also sRGB-encoded;
its embedded sine/focus previews have 8-bit display precision. These display
assets are not interchangeable with the linear NPY. Metadata provide the
reflectance endpoints, active-area coordinates, all scene geometry, patch
indices/values, frequency conventions, sampling and generator fingerprints.

Keep the original aspect ratios: CIPA/e-SFR are 8192×5783; the default 3×3 sine
chart is 8192×6201. CIPA frequency labels use the **200 mm active height**, not
the 240 mm outer-frame height. Fit the target into a sensor canvas during
simulation instead of stretching it.

## Public references used

- [Official CIPA instructions, 2022](https://www.cipa.jp/dcs/hyres/parts/TCPF_220309_e.pdf):
  dimensions, five-line wedges, frequency intervals, and the 3307×2340 illustration.
  That illustration already contains fine-pattern aliasing, so its pixels are
  not traced or upscaled as simulation ground truth.
- [Parulski et al., 2022](https://library.imaging.org/ei/articles/34/9/IQSP-347):
  standard authors' CC BY 4.0 paper. Figures 8 and 13 support sine-cell and
  slanted-star layouts, and Figure 12 provides another CIPA example.
- [IS&T resources](https://www.imaging.org/IST/IST/Standards/Digital_Camera_Resolution_Tools.aspx):
  official chart families and the preferred 4:1 slanted-star example.
- [Applied Image QA100 public specifications](https://www.appliedimage.com/wp-content/uploads/2023/04/QA-100_spec_v1-00-1.pdf)
  and its public product preview: corroborate 340×240 / 300×200 mm sizes,
  4:1 edge contrast and 20:1 OECF contrast. We reconstruct the chart features,
  not vendor logos or a vendor calibration certificate.
- [Image Engineering TE253 data sheet](https://www.image-engineering.de/content/products/charts/te253_9x/downloads/TE253_9x_data_sheet.pdf):
  primary confirmation of nine stars, sixteen patches per star and 144/72 cycles.
- A publicly accessible **old 2014 reference** provides dimensional drawings
  A.3–A.5 and the detailed single-cell layout in table E.2. Its coordinates are
  recorded as older-reference evidence, not final 2024 verification. The
  original file remains local and ignored; the URL and fingerprint are in the
  reference inventory.
- Indexed final-2024 table excerpts corroborate 5°/45° slanted-star geometry,
  0.20/0.05 reflectance, star size, and sine-star parameters. They are explicitly
  marked provisional because a complete verifiable file was not obtained.

## What is approximate or selected

CIPA main/peripheral pattern positions and squares are manually measured from
the public illustration. Older drawings supply reference lengths and radii.
We use ideal analytic wedges, integrated-frequency sweeps, selected quiet zones,
and outlined Liberation Sans labels. Small asymmetries, scan artefacts, footer
text and exact glyph appearance are not reproduced. No 0.2 mm placement
accuracy or certified 5% line-width tolerance is claimed.

The e-SFR star-centre layout is inferred from the authors' preview and its
field positions; marker size and placement are measured approximately. The
16 OECF values are a **selected logarithmic 20:1 sequence**, not an assertion
that this is the ISO14524 prescribed patch sequence. Their actual synthetic
values and ordering are supplied for repeatable simulation. The miniature
focus zone plate uses our chosen quadratic phase with different density on
its two halves.

The sine-cell's 290×270 mm dimensions, 250 mm star diameter and patch positions
come from the old public table E.2. The 3×3 arrangement uses an estimated
100 mm horizontal gap. Centre radius (one tenth of star radius), phase, finite
reflectance endpoints and gap shade are recorded choices. The top-right white
marker hole uses y=6 mm to match the visible symmetric example; the old table
lists y=0, so this override is explicit.

## Mathematical patterns and sampling

For a wedge, axial distance `s` spans length `L`, and transverse distance is `u`:

```
f(s) = f0 + (f1-f0)*s/L                    # LW/PH
w(s) = H/f(s)                            # transverse width, H=200 mm
stripe boundaries = (k ± 0.5)*w(s)        # k=-4,-2,0,2,4
```

Labels express transverse frequency, not the geometric normal to every curved
boundary. SVG contours use 512 geometrically spaced frequency samples per side;
linear NPY evaluation uses the formula directly.

Sweep phase integrates cycles per millimetre, avoiding a factor-of-two frequency
error from multiplying a varying frequency by position:

```
phase(s) = f0*s/(2*H) + (f1-f0)*s*s/(4*H*L)
black when floor(2*phase(s)) is even
```

Sine stars evaluate `mean + amplitude*cos(N*theta + phase)` directly in float.
Local tangential frequency is `N/(2*pi*r)` cycles/mm. The inner mask replaces
the singular centre with alternating quadrants. SVG stores one generated
sRGB bitmap per star type and reuses it; its sample resolution is recorded.
Generate again at a new width to obtain new linear samples, rather than enlarging
an existing SVG's embedded bitmap.

Rasterization integrates a fixed global subpixel grid in 16-row tiles; it does
not use MuPDF clipping for measurement patterns. Float32 storage does not imply
exact integration: increasing `--supersample` improves boundary/fine-frequency
sampling. Very small outputs can undersample the finest patterns, especially
nine 144-cycle stars; the JSON reports maximum unmasked sine frequency per pixel.
Labels use a separate native-resolution 8-bit coverage mask. Their coverage is
the remaining raster-only component; choose measurement ROIs that avoid labels.

## Validation and limits

[Contact sheet](../charts/modern-contact-sheet.png) ·
[Numerical validation report](../reports/modern/validation.json)

All 19 unit tests pass. Fixed-grid sampling is exactly independent of tile
height. Public draft e-SFR centre measurements differ by at most 2.2612 mm
from the inferred field-position layout; this includes manual crop/pixel
uncertainty and is not an ISO tolerance assessment.

At the delivered 8192-pixel width, selected 64×64 measurement ROIs give the
following errors for 4×4 sampling relative to an approximate 16×16 reference:

| Chart | Largest ROI maximum error | Largest ROI mean error |
|---|---:|---:|
| CIPA | 0.09834 | 0.01666 |
| e-SFR | 0.01407 | 0.000356 |
| s-SFR | 0.05974 | 0.000823 |

These are absolute linear-reflectance differences; they are not whole-image
error bounds. CIPA's sharp boundaries and the sine centre-mask boundary are
particularly sensitive to finite subpixel integration. Choose
`--supersample 8` or `--supersample 16` for more precise numerical experiments;
the report includes the 8×8 comparisons. The analytic pattern definitions are
continuous, while every saved NPY is a finite sampling of those definitions.
The separate 512-pixel convergence experiment intentionally demonstrates that
small previews cannot represent all the chart's fine features.


```bash
python -m unittest discover -s tests -v
# Reproduce the published examples and matching local NPY inputs before production validation.
for chart in cipa esfr2024 ssfr; do
  python -m iso12233.generate_chart --chart "$chart" \
    --output "charts/$chart/chart.svg" --png "charts/$chart/preview-8192.png" \
    --metadata "charts/$chart/metadata.json" --linear "output/linear/$chart.npy" --width 8192
done
python -m iso12233.validate_modern_charts --output output/validation/modern
```

Checks include the old chart's independent source geometry, 4:1 linear edge
values, all patch indices, the sine harmonic/amplitude, five-line wedge widths,
integrated sweep phase, exact tile independence on fixed grids, embedded SVG
assets, and complete CLI output metadata. The validation report records sampling
convergence, low-resolution reference-anchor differences and production-output
fingerprints; those checks do not certify the full ISO measurement procedure.

The older `linear_output.py` path for the legacy chart still uses MuPDF and has
its documented clipping differences in [the earlier report](../reports/iso2000/linear-sampling.json).
The new modern measurement-pattern backend does not share that limitation.

Source code is MIT under LICENSE. Chart artwork/data/images remain excluded
from that code license; public accessibility is not a CC0 grant. See [NOTICE](../NOTICE).
