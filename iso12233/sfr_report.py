"""Two-panel sharpness report: edge profile (top) and MTF (bottom).

Needs matplotlib (``pip install -r requirements-sfr.txt``).

    python -m iso12233.sfr_report roi.npy --title "Reference" --output report.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from iso12233.sfr import NYQUIST, EdgeReport, analyze

INK, INK2, INK3, LINE = "#1a1a1a", "#555555", "#888888", "#e5e5e5"
CURVE, ACCENT = "#2a78d6", "#eb6834"


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK3)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)


def _box(ax, lines, x=0.98, y=0.95, ha="right"):
    ax.text(x, y, "\n".join(lines), transform=ax.transAxes, ha=ha, va="top", family="monospace",
            fontsize=9, color=INK, linespacing=1.5,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=LINE))


def plot_report(r: EdgeReport, title: str = "", path: Path | None = None, dpi: int = 150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.0, 6.6), gridspec_kw={"height_ratios": [1, 1.15]})
    fig.subplots_adjust(left=0.11, right=0.97, top=0.93, bottom=0.08, hspace=0.32)
    if title:
        fig.suptitle(title, x=0.11, ha="left", fontsize=12, color=INK, fontweight="semibold")

    # edge profile
    _style(ax1)
    keep = np.abs(r.x) <= 8
    ax1.plot(r.x[keep], r.esf[keep], color=CURVE, linewidth=1.8)
    ax1.axhline(0, color=INK3, linewidth=0.8)
    ax1.axhline(1, color=INK3, linewidth=0.8)
    for lvl in (0.1, 0.9):
        ax1.axhline(lvl, color=INK3, linewidth=0.8, linestyle=(0, (2, 3)))
    ax1.set_xlim(-8, 8)
    lo = min(-0.05, float(r.esf[keep].min()) - 0.05)
    hi = max(1.1, float(r.esf[keep].max()) + 0.05)
    ax1.set_ylim(lo, hi)
    ax1.set_xlabel("distance from edge (pixels)", fontsize=9, color=INK2)
    ax1.set_ylabel("edge profile (linear)", fontsize=9, color=INK2)
    lines = [f"10–90% rise  {r.rise_10_90:5.2f} px"]
    if r.overshoot >= 1 or r.undershoot >= 1:
        lines += [f"overshoot    {r.overshoot:5.1f} %", f"undershoot   {r.undershoot:5.1f} %"]
    _box(ax1, lines, x=0.02, y=0.95, ha="left")

    # MTF
    _style(ax2)
    keep = r.freq <= 1.0
    ax2.axvspan(NYQUIST, 1.0, color="#f2f2f0", zorder=0)
    ax2.text(NYQUIST + 0.01, 0.03, "above Nyquist", fontsize=8, color=INK3, transform=ax2.get_xaxis_transform())
    ax2.plot(r.freq[keep], r.mtf[keep], color=CURVE, linewidth=1.8)
    ax2.axvline(NYQUIST, color=INK3, linewidth=0.8)
    ax2.axhline(0.5, color=INK3, linewidth=0.8, linestyle=(0, (2, 3)))
    ax2.plot([r.mtf50], [0.5], "o", color=CURVE, markersize=5, zorder=3)
    peak = float(r.mtf[r.freq <= NYQUIST].max())
    if peak > 1.02:
        ax2.axhline(0.5 * peak, color=ACCENT, linewidth=0.8, linestyle=(0, (2, 3)))
        ax2.plot([r.mtf50p], [0.5 * peak], "o", color=ACCENT, markersize=5, zorder=3)
    ax2.set_xlim(0, 1.0)
    ax2.set_ylim(0, max(1.1, float(r.mtf[keep].max()) * 1.08))
    ax2.set_xlabel("frequency (cycles/pixel)", fontsize=9, color=INK2)
    ax2.set_ylabel("MTF", fontsize=9, color=INK2)
    at = r.mtf_at
    _box(ax2, [
        f"MTF50      {r.mtf50:5.3f} c/p",
        f"MTF50P     {r.mtf50p:5.3f} c/p",
        f"MTF@0.125  {at.get(0.125, float('nan')):5.3f}",
        f"MTF@0.25   {at.get(0.25, float('nan')):5.3f}",
        f"MTF@Nyq    {at.get(NYQUIST, float('nan')):5.3f}",
    ])
    if path is not None:
        fig.savefig(path, dpi=dpi, facecolor="white")
        plt.close(fig)
    return fig


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Two-panel slanted-edge sharpness report.")
    p.add_argument("roi", type=Path, help="Linear single-channel slanted-edge ROI (.npy)")
    p.add_argument("--title", default="")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    plot_report(analyze(np.load(a.roi)), a.title, a.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
