"""How MTF curves relate to image appearance: sharpening and blur on one edge and one photo.

The edge comes from this repository's e-SFR chart (``esfr2024`` linear
reflectance, rendered at 4x the analysis resolution). A Gaussian optics PSF is
applied at that resolution and the result is area-downsampled 4x, so the
reference edge includes the pixel aperture. Each condition then applies the
same filter to the edge and to a photo crop. Filters run on sRGB-encoded
values, as an editor's sharpen/blur would; the edge is decoded back to linear
before SFR analysis.

    python -m iso12233.generate_chart --chart esfr2024 --output out/chart.svg \\
        --linear out/esfr8192.npy --width 8192 --supersample 4
    python -m iso12233.sfr_appearance --chart-npy out/esfr8192.npy \\
        --photo assets/photos/quebec-fire-escape.png --output reports/sfr-appearance
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from iso12233.sfr import analyze, to_dict
from iso12233.sfr_report import plot_report

OPTICS_SIGMA_PX = 0.5      # Gaussian optics blur at analysis resolution
SCALE = 4                  # chart render is SCALE x the analysis resolution
CANVAS_MM = (340.0, 240.0)
ROI_MM = (164.5, 96.0, 177.5, 108.0)   # x0, y0, x1, y1: left edge of the center star's upper-right blade

CONDITIONS = [
    # id, label, [(op, radius, amount)]
    ("reference", "Reference", []),
    ("usm-r1", "Unsharp mask, radius 1", [("usm", 1.0, 1.0)]),
    ("usm-r2", "Unsharp mask, radius 2", [("usm", 2.0, 1.0)]),
    ("blur-r1", "Gaussian blur, radius 1", [("blur", 1.0, 0)]),
    ("blur-r2", "Gaussian blur, radius 2", [("blur", 2.0, 0)]),
    ("blur-r2-usm-r2", "Blur radius 2, then unsharp mask radius 2", [("blur", 2.0, 0), ("usm", 2.0, 1.0)]),
]


def srgb_encode(lin):
    lin = np.clip(lin, 0, None)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def srgb_decode(v):
    v = np.clip(v, 0, None)
    return np.where(v <= 0.04045, v / 12.92, np.power((v + 0.055) / 1.055, 2.4))


def apply_ops(img: np.ndarray, ops) -> np.ndarray:
    """Apply blur / unsharp-mask steps per channel on float sRGB values."""
    out = img.astype(float)
    sig = lambda r: (r, r, 0) if out.ndim == 3 else r
    for op, radius, amount in ops:
        if op == "blur":
            out = gaussian_filter(out, sig(radius), mode="reflect")
        elif op == "usm":
            out = out + amount * (out - gaussian_filter(out, sig(radius), mode="reflect"))
        else:
            raise ValueError(op)
    return out


def chart_edge(chart: np.ndarray) -> np.ndarray:
    """Linear slanted-edge ROI at analysis resolution from a SCALE x chart render."""
    px_per_mm = chart.shape[1] / CANVAS_MM[0]
    pad = int(np.ceil(4 * OPTICS_SIGMA_PX * SCALE)) + SCALE
    x0, y0, x1, y1 = (int(round(v * px_per_mm)) for v in ROI_MM)
    x0, y0 = x0 - x0 % SCALE, y0 - y0 % SCALE
    x1, y1 = x1 - x1 % SCALE, y1 - y1 % SCALE
    hi = chart[y0 - pad:y1 + pad, x0 - pad:x1 + pad].astype(float)
    hi = gaussian_filter(hi, OPTICS_SIGMA_PX * SCALE, mode="nearest")[pad:-pad, pad:-pad]
    h, w = hi.shape[0] // SCALE, hi.shape[1] // SCALE
    return hi[:h * SCALE, :w * SCALE].reshape(h, SCALE, w, SCALE).mean(axis=(1, 3))


def save_png(arr01: np.ndarray, path: Path, scale: int = 1, quality: int | None = None):
    from PIL import Image
    img = Image.fromarray((np.clip(arr01, 0, 1) * 255 + 0.5).astype(np.uint8))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(path, quality=quality) if quality else img.save(path)


def run(chart_npy: Path, photo: Path, out: Path) -> dict:
    from PIL import Image
    out.mkdir(parents=True, exist_ok=True)
    edge_lin = chart_edge(np.load(chart_npy, mmap_mode="r"))
    edge_srgb = srgb_encode(edge_lin)
    photo_srgb = np.asarray(Image.open(photo).convert("RGB"), dtype=float) / 255.0

    summary = {"optics_sigma_px": OPTICS_SIGMA_PX, "roi_px": list(edge_lin.shape), "conditions": []}
    for cid, label, ops in CONDITIONS:
        e = apply_ops(edge_srgb, ops)
        r = analyze(srgb_decode(e))
        plot_report(r, label, out / f"report_{cid}.png")
        save_png(e, out / f"edge_{cid}.png", scale=4)
        save_png(apply_ops(photo_srgb, ops), out / f"photo_{cid}.jpg", quality=92)
        summary["conditions"].append({"id": cid, "label": label, "ops": ops, **to_dict(r)})
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--chart-npy", type=Path, required=True, help="esfr2024 linear reflectance, 8192 px wide")
    p.add_argument("--photo", type=Path, required=True, help="sRGB photo crop")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    s = run(a.chart_npy, a.photo, a.output)
    for c in s["conditions"]:
        print(f"{c['id']:16s} MTF50 {c['mtf50_cpp']:.3f}  MTF50P {c['mtf50p_cpp']:.3f}  "
              f"rise {c['rise_10_90_px']:.2f} px  overshoot {c['overshoot_pct']:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
