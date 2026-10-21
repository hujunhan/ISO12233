#!/usr/bin/env python3
# NumPy port of sfrmat5 by Junhan Hu.
#
# Derived from sfrmat5 (MATLAB), Copyright (c) 2015, Peter D. Burns. All rights reserved.
# http://burnsdigitalimaging.com/software/sfrmat/
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in
#       the documentation and/or other materials provided with the distribution
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""NumPy port of the non-GUI sfrmat5 MATLAB workflow.

The public entry point is ``sfrmat5(image, del_=1, npol=5, wflag=0)``.
It expects a 2-D grayscale or 3-D RGB NumPy array containing an already
selected slanted-edge ROI.  The implementation follows the MATLAB
distribution closely (same edge fit, binning, windows and derivative
correction). Analytic regression tests live in ``tests/test_sfr.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math
import struct
from typing import Iterable

import numpy as np


DEFAULT_WEIGHT = np.array([0.213, 0.715, 0.072], dtype=float)


@dataclass
class SFRResult:
    status: int
    dat: np.ndarray
    sampling_efficiency: np.ndarray
    sfr50: float | np.ndarray
    fitme: np.ndarray
    esf: np.ndarray
    nbin: int
    del2: float


def _matlab_round(x):
    """Round halves away from zero, matching MATLAB/Octave round."""
    arr = np.asarray(x)
    out = np.where(arr >= 0, np.floor(arr + 0.5), np.ceil(arr - 0.5))
    if np.isscalar(x):
        return float(out)
    return out


def _clip(in_, low, high=None):
    if high is None:
        return np.maximum(in_, low)
    return np.minimum(np.maximum(in_, low), high)


def _centroid(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).ravel()
    idx = np.arange(1, len(x) + 1, dtype=float)
    denom = np.sum(x)
    if denom == 0:
        return float("nan")
    return float(np.sum(idx * x) / denom)


def _deriv1(a: np.ndarray, fil: Iterable[float]) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    fil = np.asarray(list(fil), dtype=float)
    nlin, npix = a.shape
    b = np.zeros((nlin, npix), dtype=float)
    start = len(fil) // 2
    for ii in range(nlin):
        full = np.convolve(a[ii, :], fil, mode="full")
        b[ii, :] = full[start : start + npix]
        if npix > 1:
            b[ii, 0] = b[ii, 1]
            b[ii, -1] = b[ii, -2]
    return b


def _polyfit_convert(p2: np.ndarray, x: np.ndarray) -> np.ndarray:
    p2 = np.asarray(p2, dtype=float)
    x = np.asarray(x, dtype=float)
    n = p2.size - 1
    m = np.mean(x)
    s = np.std(x, ddof=1)
    retval = np.zeros_like(p2, dtype=float)
    for i in range(n + 1):
        for j in range(i + 1):
            retval[n - j] += (
                p2[n - i]
                * math.comb(i, j)
                * ((-m) ** (i - j))
                / (s**i)
            )
    return retval


def _findedge2(cent: np.ndarray, nlin: int, order: int) -> np.ndarray:
    index = np.arange(nlin, dtype=float)
    z = (index - np.mean(index)) / np.std(index, ddof=1)
    p_scaled = np.polyfit(z, np.asarray(cent, dtype=float), order)
    return _polyfit_convert(p_scaled, index)


def _rotate90(a: np.ndarray) -> np.ndarray:
    return np.rot90(a, k=1, axes=(0, 1))


def _rotatev2(a: np.ndarray) -> tuple[np.ndarray, int, int, int]:
    a = np.asarray(a, dtype=float)
    nlin, npix = a.shape[:2]
    mm = 1 if a.ndim == 3 and a.shape[2] > 1 else 0
    nn = 3
    testv = abs(np.mean(a[nlin - nn - 1, :, mm]) - np.mean(a[nn - 1, :, mm]))
    testh = abs(np.mean(a[:, npix - nn - 1, mm]) - np.mean(a[:, nn - 1, mm]))
    rflag = 0
    if testv > testh:
        rflag = 1
        a = _rotate90(a)
        nlin, npix = npix, nlin
    return a, nlin, npix, rflag


def _ahamming(n: int, mid: float) -> np.ndarray:
    mid = mid + 0.5
    wid1 = mid - 1
    wid2 = n - mid
    wid = max(wid1, wid2)
    i = np.arange(1, n + 1, dtype=float)
    data = np.cos(np.pi * (i - mid) / wid)
    return 0.54 + 0.46 * data


def _tukey(n: int, alpha: float = 0.5) -> np.ndarray:
    if n == 1:
        return np.ones(1, dtype=float)
    if alpha == 0:
        return np.ones(n, dtype=float)
    m = (n - 1) / 2
    w = np.zeros(n, dtype=float)
    for k in range(int(math.floor(m)) + 1):
        if k <= alpha * m:
            val = 0.5 * (1 + math.cos(math.pi * (k / alpha / m - 1)))
        else:
            val = 1.0
        w[k] = val
        w[n - k - 1] = val
    return w


def _tukey2(n: int, alpha: float = 1.0, mid: float | None = None) -> np.ndarray:
    if mid is None:
        mid = n / 2
    if n < 3:
        return np.ones(n, dtype=float)
    m1 = n / 2
    m2 = mid
    m3 = n - mid
    n2 = int(_matlab_round(2 * max(m2, m3)))
    w = _tukey(n2, alpha)
    if mid >= m1:
        return w[:n]
    return w[-n:]


def _fir2fix(n: int, m: int) -> np.ndarray:
    correct = np.ones(n, dtype=float)
    m = m - 1
    for idx in range(1, n):
        i = idx + 1
        val = abs((np.pi * i * m / (2 * (n + 1))) / math.sin(np.pi * i * m / (2 * (n + 1))))
        correct[idx] = min(val, 10)
    return correct


def _cent(a: np.ndarray, center: float) -> np.ndarray:
    a = np.asarray(a, dtype=float).ravel()
    n = len(a)
    b = np.zeros(n, dtype=float)
    mid = int(_matlab_round((n + 1) / 2))
    delta = int(_matlab_round(center - mid))
    if delta > 0:
        b[: n - delta] = a[delta:n]
    elif delta < 1:
        b[-delta:n] = a[: n + delta]
    else:
        b[:] = a
    return b


def _project2(bb: np.ndarray, fitme: np.ndarray, fac: int = 4) -> tuple[np.ndarray, int]:
    bb = np.asarray(bb, dtype=float)
    fitme = np.asarray(fitme, dtype=float)
    nlin, npix = bb.shape
    slope = 1.0 / fitme[-2]
    nn = int(math.floor(npix * fac))
    offset = int(_matlab_round(fac * (0 - (nlin - 1) / slope)))
    extra = abs(offset)
    if offset > 0:
        offset = 0
    bwidth = nn + extra + 150
    barray = np.zeros((2, bwidth), dtype=float)

    rows = np.arange(nlin, dtype=float)
    p2 = np.polyval(fitme, rows) - fitme[-1]
    cols = np.arange(npix, dtype=float)
    for m in range(nlin):
        ling = np.ceil((cols - p2[m]) * fac).astype(int) + 1 - offset
        ling = np.clip(ling, 1, bwidth) - 1
        np.add.at(barray[0], ling, 1)
        np.add.at(barray[1], ling, bb[m, :])

    point = np.zeros(nn, dtype=float)
    start = 1 + int(_matlab_round(0.5 * extra))
    start0 = start - 1
    status = 0
    for k in range(start0, start0 + nn):
        if barray[0, k] == 0:
            status = 1
            if k == 0:
                barray[:, k] = barray[:, k + 1]
            elif k == start0 + nn - 1:
                barray[:, k] = barray[:, k - 1]
            else:
                barray[:, k] = (barray[:, k - 1] + barray[:, k + 1]) / 2

    for i in range(nn):
        k = i + start0
        point[i] = barray[1, k] / barray[0, k]
    return point, status


def _findfreq(dat: np.ndarray, val: float, imax: int, fflag: int = 0) -> tuple[np.ndarray, np.ndarray]:
    dat = np.array(dat, dtype=float, copy=True)
    nc = dat.shape[1] - 1
    freqval = np.zeros(nc, dtype=float)
    sfrval = np.zeros(nc, dtype=float)
    maxf = dat[imax - 1, 0]
    fil = np.ones(3, dtype=float) / 3
    for c in range(nc):
        if fflag != 0:
            temp = np.convolve(dat[:, c + 1], fil, mode="same")
            dat[1:-1, c + 1] = temp[1:-1]
        test = dat[:, c + 1] - val
        crossing = np.where(test < 0)[0]
        if crossing.size == 0 or crossing[0] == 0:
            s = maxf
            sval = dat[imax - 1, c + 1]
        else:
            j = crossing[0]
            prev = j - 1
            sval = dat[prev, c + 1]
            s = dat[prev, 0]
            y = dat[prev, c + 1]
            y2 = dat[j, c + 1]
            slope = (y2 - y) / dat[1, 0]
            dely = test[prev]
            s = s - dely / slope
            sval = sval - dely
        if s > maxf:
            s = maxf
            sval = dat[imax - 1, c + 1]
        freqval[c] = s
        sfrval[c] = sval
    return freqval, sfrval


def _sampeff(dat: np.ndarray, val: Iterable[float], del_: float, fflag: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dat = np.asarray(dat, dtype=float)
    val = np.asarray(list(val), dtype=float)
    hs = 0.495 / del_
    if np.where(dat[:, 0] > hs)[0].size == 0:
        return np.array(0), np.array(0), np.array(0)
    nc = dat.shape[1] - 1
    nval = len(val)
    eff = np.zeros((nval, nc), dtype=float)
    freqval = np.zeros((nval, nc), dtype=float)
    sfrval = np.zeros((nval, nc), dtype=float)
    imax = dat.shape[0]
    for v, threshold in enumerate(val):
        freqval[v, :], sfrval[v, :] = _findfreq(dat, threshold, imax, fflag)
        freqval[v, :] = _clip(freqval[v, :], 0, hs)
        eff[v, :] = np.minimum(_matlab_round(100 * freqval[v, :] / hs), 100)
    return eff, freqval, sfrval


def sfrmat5(
    image: np.ndarray,
    del_: float = 1.0,
    npol: int = 5,
    wflag: int = 0,
    weight: Iterable[float] | None = None,
    nbin: int = 4,
    alpha: float = 1.0,
) -> SFRResult:
    """Compute slanted-edge SFR for an already selected ROI.

    Parameters mirror the MATLAB non-GUI path ``sfrmat5(1, del, a, npol,
    wflag, weight)``.  ``del_`` is either pixel pitch in mm or DPI when
    greater than 1, matching the original routine.
    """
    status = 0
    if weight is None:
        weight_arr = DEFAULT_WEIGHT.copy()
    else:
        weight_arr = np.asarray(list(weight), dtype=float)
        if weight_arr.shape != (3,):
            raise ValueError("weight must contain three RGB luminance weights")

    npol = min(int(npol), 5)
    alpha = float(_clip(alpha, 0.5, 1.0))
    a = np.asarray(image, dtype=float)
    if a.ndim == 2:
        a = a[:, :, None]
    if a.ndim != 3:
        raise ValueError("image must be a 2-D grayscale or 3-D RGB array")

    samp = np.zeros(3, dtype=float)
    samp[0] = nbin
    samp[1] = del_
    if del_ > 1:
        del_ = 25.4 / del_

    nlin, npix, ncol = a.shape
    if ncol == 3:
        lum = weight_arr[0] * a[:, :, 0] + weight_arr[1] * a[:, :, 1] + weight_arr[2] * a[:, :, 2]
        a = np.stack((a[:, :, 0], a[:, :, 1], a[:, :, 2], lum), axis=2)
        ncol = 4

    a, nlin, npix, rflag = _rotatev2(a)
    loc = np.zeros((ncol, nlin), dtype=float)

    fil1 = np.array([0.5, -0.5], dtype=float)
    fil2 = np.array([0.5, 0.0, -0.5], dtype=float)
    tleft = np.sum(a[:, :5, 0])
    tright = np.sum(a[:, npix - 6 : npix, 0])
    if tleft > tright:
        fil1 = np.array([-0.5, 0.5], dtype=float)
        fil2 = np.array([-0.5, 0.0, 0.5], dtype=float)

    fitme = np.zeros((ncol, npol + 1), dtype=float)
    fitme1 = np.zeros((ncol, 2), dtype=float)
    if wflag != 0:
        win1 = _ahamming(npix, (npix + 1) / 2)
    else:
        win1 = 0.95 * _tukey2(npix, alpha, (npix + 1) / 2) + 0.05

    for color in range(ncol):
        c = _deriv1(a[:, :, color], fil1)
        for n in range(nlin):
            loc[color, n] = _centroid(c[n, :] * win1) - 0.5
        fitme[color, :] = _findedge2(loc[color, :], nlin, npol)

        rows = np.arange(nlin, dtype=float)
        place = np.polyval(fitme[color, :], rows)
        for n in range(nlin):
            if wflag != 0:
                win2 = _ahamming(npix, place[n])
            else:
                win2 = 0.95 * _tukey2(npix, alpha, place[n]) + 0.05
            loc[color, n] = _centroid(c[n, :] * win2) - 0.5

        fitme[color, :] = _findedge2(loc[color, :], nlin, npol)
        fitme1[color, :] = _findedge2(loc[color, :], nlin, 1)

    midloc = np.array([np.polyval(fitme[i, :], (nlin - 1) / 2) for i in range(ncol)])
    slout = -fitme1[:, -2]
    slout = 180 * np.arctan(slout) / np.pi
    if rflag == 1:
        slout += 90
    misreg = midloc - midloc[1] if ncol > 2 else None

    last_slope = abs(fitme1[-1, -2])
    nlin1 = int(_matlab_round(math.floor(nlin * last_slope) / last_slope))
    a = a[:nlin1, :, :ncol]
    nlin = nlin1

    vslope = -fitme1[-1, -2]
    delimage = del_
    delfac = math.cos(math.atan(vslope))
    del_normal = del_ * delfac
    del2 = del_normal / nbin
    samp[2] = del2
    if misreg is not None:
        misreg = delfac * misreg

    nn = int(math.ceil(npix * nbin))
    mtf = np.zeros((nn, ncol), dtype=float)
    nn2 = int(math.floor(nn / 2) + 1)
    dcorr = _fir2fix(nn2, 3)
    freqlim = 2 if nbin == 1 else 1
    nn2out = int(_matlab_round(nn2 * freqlim / 2))

    esf_profiles = np.zeros((nn, ncol), dtype=float)
    for color in range(ncol):
        esf, pstatus = _project2(a[:, :, color], fitme[color, :], nbin)
        status = max(status, pstatus)
        esf_profiles[:, color] = esf[:nn]
        c = _deriv1(esf.reshape(1, -1), fil2).ravel()
        if c[0] == 0:
            c[0] = c[1]
        elif c[-1] == 0:
            c[-1] = c[-2]
        max_locs = np.where(c == np.max(c))[0] + 1
        mm = float(np.mean(max_locs))
        c = _cent(c, mm)
        mm = nn / 2
        win = _ahamming(nn, mm) if wflag != 0 else _tukey2(nn, alpha, mm)
        c = win * c.ravel()
        temp = np.abs(np.fft.fft(c, nn))
        mtf[:nn2, color] = temp[:nn2] / temp[0]
        mtf[:nn2, color] *= dcorr

    freq = np.arange(nn, dtype=float) / (del2 * nn)
    dat = np.column_stack((freq[:nn2out], mtf[:nn2out, :]))

    if ncol > 2:
        fitme_out = np.zeros((ncol, npol + 2), dtype=float)
        fitme_out[:, : npol + 1] = fitme
        fitme_out[:, -1] = misreg
    else:
        fitme_out = fitme

    e, freqval, _ = _sampeff(dat, [0.1, 0.5], delimage, 0)
    sfr50 = float(freqval.ravel(order="F")[1])
    return SFRResult(status, dat, e, sfr50, fitme_out, esf_profiles, nbin, del2)


def _load_image(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path)
    if suffix == ".bmp":
        return _read_bmp(path)

    loaders = []
    try:
        from PIL import Image  # type: ignore

        loaders.append(lambda p: np.asarray(Image.open(p)))
    except Exception:
        pass
    try:
        import imageio.v3 as iio  # type: ignore

        loaders.append(lambda p: iio.imread(p))
    except Exception:
        pass
    try:
        import tifffile  # type: ignore

        loaders.append(lambda p: tifffile.imread(p))
    except Exception:
        pass
    try:
        import matplotlib.image as mpimg  # type: ignore

        loaders.append(lambda p: mpimg.imread(p))
    except Exception:
        pass

    for loader in loaders:
        try:
            return np.asarray(loader(path))
        except Exception:
            continue

    raise RuntimeError(
        "No image loader is available. Install Pillow/imageio/tifffile, "
        "or pass a .npy array containing the ROI."
    )


def _read_bmp(path: Path) -> np.ndarray:
    """Read common uncompressed BMP files without extra dependencies."""
    data = Path(path).read_bytes()
    if data[:2] != b"BM":
        raise ValueError(f"{path} is not a BMP file")
    pixel_offset = struct.unpack_from("<I", data, 10)[0]
    dib_size = struct.unpack_from("<I", data, 14)[0]
    if dib_size < 40:
        raise ValueError("Unsupported BMP DIB header")
    width = struct.unpack_from("<i", data, 18)[0]
    height_signed = struct.unpack_from("<i", data, 22)[0]
    planes = struct.unpack_from("<H", data, 26)[0]
    bits = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]
    if planes != 1 or compression != 0 or width <= 0:
        raise ValueError("Only uncompressed BMP images are supported")

    top_down = height_signed < 0
    height = abs(height_signed)
    if bits == 24:
        channels = 3
        row_bytes = ((width * 3 + 3) // 4) * 4
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for row in range(height):
            src_row = row if top_down else height - row - 1
            start = pixel_offset + src_row * row_bytes
            raw = np.frombuffer(data, dtype=np.uint8, count=width * 3, offset=start)
            arr[row, :, :] = raw.reshape(width, channels)[:, ::-1]
        if np.array_equal(arr[:, :, 0], arr[:, :, 1]) and np.array_equal(arr[:, :, 1], arr[:, :, 2]):
            return arr[:, :, 0]
        return arr
    if bits == 32:
        row_bytes = width * 4
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        for row in range(height):
            src_row = row if top_down else height - row - 1
            start = pixel_offset + src_row * row_bytes
            raw = np.frombuffer(data, dtype=np.uint8, count=width * 4, offset=start)
            arr[row, :, :] = raw.reshape(width, 4)[:, 2::-1]
        if np.array_equal(arr[:, :, 0], arr[:, :, 1]) and np.array_equal(arr[:, :, 1], arr[:, :, 2]):
            return arr[:, :, 0]
        return arr
    if bits == 8:
        colors_used = struct.unpack_from("<I", data, 46)[0] if dib_size >= 40 else 0
        ncolors = colors_used or 256
        palette_start = 14 + dib_size
        palette = np.frombuffer(data, dtype=np.uint8, count=ncolors * 4, offset=palette_start).reshape(ncolors, 4)
        palette_rgb = palette[:, 2::-1]
        row_bytes = ((width + 3) // 4) * 4
        idx = np.zeros((height, width), dtype=np.uint8)
        for row in range(height):
            src_row = row if top_down else height - row - 1
            start = pixel_offset + src_row * row_bytes
            idx[row, :] = np.frombuffer(data, dtype=np.uint8, count=width, offset=start)
        arr = palette_rgb[idx]
        if np.array_equal(arr[:, :, 0], arr[:, :, 1]) and np.array_equal(arr[:, :, 1], arr[:, :, 2]):
            return arr[:, :, 0]
        return arr
    raise ValueError(f"Unsupported BMP bit depth: {bits}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute SFR using the Python sfrmat5 port.")
    parser.add_argument("image", type=Path, help="Input ROI image or .npy array")
    parser.add_argument("--del", dest="del_", type=float, default=1.0, help="Sampling interval or DPI")
    parser.add_argument("--npol", type=int, default=5, help="Polynomial edge fit order, max 5")
    parser.add_argument("--wflag", type=int, default=0, help="0 for Tukey, nonzero for Hamming")
    parser.add_argument("--csv", type=Path, help="Optional CSV path for frequency/SFR data")
    args = parser.parse_args(argv)

    image = _load_image(args.image)
    result = sfrmat5(image, del_=args.del_, npol=args.npol, wflag=args.wflag)
    print(f"status: {result.status}")
    print(f"dat shape: {result.dat.shape[0]} x {result.dat.shape[1]}")
    print("sampling efficiency:")
    print(result.sampling_efficiency.astype(int))
    print(f"sfr50: {result.sfr50}")
    if args.csv:
        np.savetxt(args.csv, result.dat, delimiter=",")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
