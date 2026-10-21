"""Slanted-edge sharpness metrics on top of the sfrmat5 port.

``analyze(roi)`` runs sfrmat5 on a linear, single-channel slanted-edge ROI and
adds the edge-profile and MTF summary numbers used in sharpness reports:
10-90% rise distance, overshoot/undershoot, MTF50, MTF50P (50% of the MTF
peak, which stays meaningful for sharpened images whose MTF exceeds 1) and
MTF at fixed frequencies. Frequencies are in cycles/pixel; distances in pixels.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from iso12233.sfrmat5 import sfrmat5

NYQUIST = 0.5


@dataclass
class EdgeReport:
    x: np.ndarray            # ESF sample positions, pixels, 0 at the 50% crossing
    esf: np.ndarray          # ESF normalized to 0 (dark plateau) .. 1 (light plateau)
    freq: np.ndarray         # cycles/pixel
    mtf: np.ndarray
    rise_10_90: float        # pixels
    overshoot: float         # percent of the step, light side
    undershoot: float        # percent of the step, dark side
    mtf50: float
    mtf50p: float
    mtf_at: dict = field(default_factory=dict)
    edge_angle: float = float("nan")  # degrees from vertical


def _crossing(x: np.ndarray, y: np.ndarray, level: float, start: int, step: int) -> float:
    """Linear-interpolated position where y crosses ``level``, walking from ``start`` by ``step``."""
    i = start
    while 0 <= i + step < len(y):
        a, b = y[i], y[i + step]
        if (a - level) * (b - level) <= 0 and a != b:
            t = (level - a) / (b - a)
            return float(x[i] + t * (x[i + step] - x[i]))
        i += step
    return float("nan")


def normalize_esf(esf: np.ndarray, tail: float = 0.15) -> tuple[np.ndarray, float, float]:
    """Scale an ESF to 0..1 using medians of its two tails, rising left to right."""
    esf = np.asarray(esf, dtype=float)
    n = max(3, int(len(esf) * tail))
    lo, hi = float(np.median(esf[:n])), float(np.median(esf[-n:]))
    if hi < lo:
        esf, lo, hi = esf[::-1], hi, lo
    return (esf - lo) / (hi - lo), lo, hi


def edge_profile_metrics(x: np.ndarray, e: np.ndarray) -> tuple[float, float, float, np.ndarray]:
    """10-90% rise and over/undershoot of a normalized, rising ESF; also returns x re-centered at 50%."""
    grad = np.gradient(e)
    peak = int(np.argmax(grad))
    x50 = _crossing(x, e, 0.5, peak, 1)
    if np.isnan(x50):
        x50 = _crossing(x, e, 0.5, peak, -1)
    i50 = int(np.searchsorted(x, x50))
    x10 = _crossing(x, e, 0.1, i50, -1)
    x90 = _crossing(x, e, 0.9, max(i50 - 1, 0), 1)
    overshoot = max(0.0, float(np.max(e[i50:]) - 1.0)) * 100.0
    undershoot = max(0.0, float(-np.min(e[:i50 + 1]))) * 100.0
    return x90 - x10, overshoot, undershoot, x - x50


def mtf_level_crossing(freq: np.ndarray, mtf: np.ndarray, level: float, start: int = 0) -> float:
    """First frequency at or after index ``start`` where the MTF falls below ``level``."""
    for i in range(start, len(mtf) - 1):
        if mtf[i] >= level > mtf[i + 1]:
            return float(freq[i] + (mtf[i] - level) / (mtf[i] - mtf[i + 1]) * (freq[i + 1] - freq[i]))
    return float("nan")


def mtf_metrics(freq: np.ndarray, mtf: np.ndarray, at=(0.125, 0.25, NYQUIST)) -> tuple[float, float, dict]:
    """MTF50, MTF50P and MTF at fixed frequencies.

    MTF50P uses the peak at or below Nyquist, as Imatest-style reports do, so a
    sharpening boost is measured from its top rather than from 1.
    """
    mtf50 = mtf_level_crossing(freq, mtf, 0.5)
    band = freq <= NYQUIST + 1e-9
    ipk = int(np.argmax(np.where(band, mtf, -np.inf)))
    mtf50p = mtf_level_crossing(freq, mtf, 0.5 * mtf[ipk], ipk)
    values = {float(f): float(np.interp(f, freq, mtf)) for f in at}
    return mtf50, mtf50p, values


def analyze(roi: np.ndarray, nbin: int = 4, npol: int = 5) -> EdgeReport:
    """Run sfrmat5 on a linear, single-channel slanted-edge ROI and summarize it."""
    roi = np.asarray(roi, dtype=float)
    if roi.ndim != 2:
        raise ValueError("analyze() expects a single-channel ROI; convert to luminance first")
    res = sfrmat5(roi, del_=1.0, npol=npol, nbin=nbin)
    esf = res.esf[:, 0]
    x = np.arange(len(esf), dtype=float) * res.del2
    e, _, _ = normalize_esf(esf)
    rise, over, under, xc = edge_profile_metrics(x, e)
    freq, mtf = res.dat[:, 0], res.dat[:, 1]
    mtf50, mtf50p, at = mtf_metrics(freq, mtf)
    slope = res.fitme[0, -2] if res.fitme.ndim == 2 else float("nan")
    return EdgeReport(xc, e, freq, mtf, rise, over, under, mtf50, mtf50p, at,
                      float(np.degrees(np.arctan(abs(slope)))))


def to_dict(r: EdgeReport) -> dict:
    """JSON-friendly summary (no arrays)."""
    return {
        "rise_10_90_px": round(r.rise_10_90, 4),
        "overshoot_pct": round(r.overshoot, 2),
        "undershoot_pct": round(r.undershoot, 2),
        "mtf50_cpp": round(r.mtf50, 4),
        "mtf50p_cpp": round(r.mtf50p, 4),
        "mtf_at": {f"{k:g}": round(v, 4) for k, v in r.mtf_at.items()},
        "edge_angle_deg": round(r.edge_angle, 2),
    }
