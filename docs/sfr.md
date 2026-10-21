# Slanted-edge SFR and image appearance

`iso12233/sfrmat5.py` is a NumPy port of Peter Burns's sfrmat5 (MATLAB, BSD
license): edge-location fit, 4x super-sampled projection, windowing, FFT and
derivative correction. `iso12233/sfr.py` adds the summary numbers used in
sharpness reports, and `iso12233/sfr_report.py` draws them.

```bash
pip install -r requirements-sfr.txt            # matplotlib, for plots only
python -m iso12233.sfr_report roi.npy --title "My lens" --output report.png
```

`analyze(roi)` expects a **linear**, single-channel ROI containing one
near-vertical or near-horizontal slanted edge. Decode sRGB or gamma-encoded
images before analysis.

## Metrics

| Metric | Definition |
|---|---|
| 10–90% rise | Distance (px) between the 10% and 90% points of the edge profile, normalized to medians of its two flat tails |
| Overshoot / undershoot | Peak above the light plateau / below the dark plateau, % of the step |
| MTF50 | First frequency (cycles/pixel) where MTF falls below 0.5 |
| MTF50P | First frequency after the MTF peak (at or below Nyquist) where MTF falls below half that peak. Equals MTF50 when the MTF is monotone; for sharpened images it measures the curve from its top instead of from 1 |
| MTF@f | MTF at 0.125, 0.25 and 0.5 (Nyquist) cycles/pixel |

## Validation

`tests/test_sfr.py` point-samples closed-form edge spread functions at a 5°
slant, so the true MTF is known exactly.

| Edge | Check | Measured | Closed form |
|---|---|---|---|
| Gaussian σ = 0.6 px | MTF50 | 0.311 | 0.312 |
| Gaussian σ = 1.0 px | MTF50 · 10–90% rise | 0.187 · 2.58 px | 0.187 · 2.56 px |
| Gaussian σ = 1.5 px | MTF50 | 0.125 | 0.125 |
| Gaussian σ = 0.6 px + unsharp mask r = 2, amount 1 | MTF50 · MTF50P · MTF peak · overshoot | 0.438 · 0.362 · 1.549 · 23.5% | 0.442 · 0.364 · 1.560 · 23.8% |

MTF50 is within 1% of the closed form in every case (largest error 0.8%, the
unsharp-mask edge), the MTF stays within 0.02 of the closed form up to Nyquist
for every Gaussian case, and the fitted edge angle is within 0.2° of the true 5°.
The tests enforce these tolerances; closed-form values are computed in the test
from the same ESF/MTF expressions.

## How MTF relates to appearance

`python -m iso12233.sfr_appearance` reproduces the idea of Imatest's
"MTF curves and image appearance" page with open inputs. The edge is cut from
this repository's e-SFR chart (center star, 0.05/0.20 reflectance), rendered
at 4x, blurred by a Gaussian optics PSF (σ = 0.5 px at analysis resolution)
and area-downsampled, so the reference includes the pixel aperture. Each
condition applies the same filter to that edge and to a photo crop. Filters run
on sRGB-encoded values, as a photo editor would; the edge is decoded back to
linear before analysis.

| Condition | MTF50 | MTF50P | 10–90% rise | Overshoot |
|---|---|---|---|---|
| Reference | 0.322 | 0.322 | 1.50 px | 0% |
| Unsharp mask, radius 1 | 0.455 | 0.425 | 0.92 px | 15.2% |
| Unsharp mask, radius 2 | 0.472 | 0.385 | 0.75 px | 35.6% |
| Gaussian blur, radius 1 | 0.166 | 0.166 | 2.93 px | 0% |
| Gaussian blur, radius 2 | 0.093 | 0.093 | 5.22 px | 0% |
| Blur r 2, then unsharp mask r 2 | 0.123 | 0.123 | 3.78 px | 4.1% |

Outputs, one set per condition, are in [reports/sfr-appearance](../reports/sfr-appearance):
`report_*.png` (edge profile + MTF), `edge_*.png` (ROI, 4x nearest-neighbour)
and `photo_*.jpg`, plus `summary.json`.

What to read from them:

- Sharpening lifts mid frequencies above 1. The hump in the MTF is the halo
  (overshoot) on the edge, and MTF50 overstates the gain; MTF50P is the
  fairer number.
- A larger unsharp-mask radius moves the hump to lower frequencies and makes
  the halo wider and more visible.
- Sharpening after a strong blur restores some edge contrast but little
  resolution: the MTF above ~0.2 cycles/pixel is already gone.

These numbers come from a synthetic edge and are not comparable one-to-one with
Imatest's table, which was measured on a photographed chart with Photoshop
filters. Only the qualitative relationships are expected to agree.

Photo: crop of "Stone building facade with small windows in Quebec City" by
Wilfredor, CC0, Wikimedia Commons (see NOTICE).
