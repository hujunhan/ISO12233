"""Analytic regression tests for the sfrmat5 port and the sharpness metrics.

Edges are point-sampled from closed-form edge spread functions, so the true MTF
is known exactly:
  Gaussian PSF (sigma):      MTF(f) = exp(-2 pi^2 sigma^2 f^2)
  + unsharp mask (r, k):     MTF(f) * (1 + k (1 - exp(-2 pi^2 r^2 f^2)))
"""
import math
import unittest

import numpy as np
from scipy.special import ndtr

from iso12233.sfr import analyze, mtf_level_crossing, mtf_metrics

DARK, LIGHT = 0.05, 0.20          # e-SFR 4:1 edge contrast


def slanted_edge(esf, angle_deg=5.0, rows=128, cols=96):
    """Point-sample ``esf(d)`` at pixel centers; d = signed distance (px) to a near-vertical edge."""
    t = math.tan(math.radians(angle_deg))
    y, x = np.mgrid[0:rows, 0:cols] + 0.5
    d = ((x - cols / 2) - t * (y - rows / 2)) * math.cos(math.radians(angle_deg))
    return DARK + (LIGHT - DARK) * esf(d)


def gauss_esf(sigma):
    return lambda d: ndtr(d / sigma)


def usm_esf(sigma, radius, amount):
    blurred = math.hypot(sigma, radius)
    return lambda d: ndtr(d / sigma) + amount * (ndtr(d / sigma) - ndtr(d / blurred))


def gauss_mtf(f, sigma):
    return np.exp(-2 * math.pi ** 2 * sigma ** 2 * f ** 2)


def usm_mtf(f, sigma, radius, amount):
    return gauss_mtf(f, sigma) * (1 + amount * (1 - gauss_mtf(f, radius)))


class GaussianEdgeTests(unittest.TestCase):
    def test_mtf_matches_closed_form(self):
        for sigma in (0.6, 1.0, 1.5):
            with self.subTest(sigma=sigma):
                r = analyze(slanted_edge(gauss_esf(sigma)))
                band = r.freq <= 0.5
                err = np.abs(r.mtf[band] - gauss_mtf(r.freq[band], sigma))
                self.assertLess(err.max(), 0.02)
                self.assertAlmostEqual(r.mtf50, 0.18739 / sigma, delta=0.01 * 0.18739 / sigma)

    def test_rise_distance_and_no_overshoot(self):
        for sigma in (0.6, 1.0, 1.5):
            with self.subTest(sigma=sigma):
                r = analyze(slanted_edge(gauss_esf(sigma)))
                self.assertAlmostEqual(r.rise_10_90, 2.5631 * sigma, delta=0.04 * 2.5631 * sigma)
                self.assertLess(r.overshoot, 0.5)
                self.assertLess(r.undershoot, 0.5)

    def test_mtf50p_equals_mtf50_for_monotone_mtf(self):
        r = analyze(slanted_edge(gauss_esf(1.0)))
        self.assertAlmostEqual(r.mtf50p, r.mtf50, delta=0.01)

    def test_edge_angle(self):
        r = analyze(slanted_edge(gauss_esf(1.0), angle_deg=5.0))
        self.assertAlmostEqual(r.edge_angle, 5.0, delta=0.2)


class UnsharpMaskTests(unittest.TestCase):
    SIGMA, RADIUS, AMOUNT = 0.6, 2.0, 1.0

    def setUp(self):
        self.r = analyze(slanted_edge(usm_esf(self.SIGMA, self.RADIUS, self.AMOUNT)))
        self.f = np.linspace(0, 1, 4001)
        self.true = usm_mtf(self.f, self.SIGMA, self.RADIUS, self.AMOUNT)

    def test_mtf_peak_above_one(self):
        band = self.r.freq <= 0.5
        self.assertAlmostEqual(self.r.mtf[band].max(), self.true[self.f <= 0.5].max(), delta=0.03)
        self.assertGreater(self.r.mtf[band].max(), 1.2)

    def test_mtf50_matches_closed_form(self):
        true50, _, _ = mtf_metrics(self.f, self.true)
        self.assertAlmostEqual(self.r.mtf50, true50, delta=0.01 * true50)

    def test_mtf50p_matches_closed_form(self):
        _, true50p, _ = mtf_metrics(self.f, self.true)
        self.assertAlmostEqual(self.r.mtf50p, true50p, delta=0.03 * true50p)
        self.assertGreater(self.r.mtf50, self.r.mtf50p)

    def test_overshoot_matches_closed_form(self):
        d = np.linspace(-20, 20, 40001)
        true_over = (usm_esf(self.SIGMA, self.RADIUS, self.AMOUNT)(d).max() - 1) * 100
        self.assertAlmostEqual(self.r.overshoot, true_over, delta=2.0)
        self.assertAlmostEqual(self.r.undershoot, true_over, delta=2.0)   # symmetric halo


class HelperTests(unittest.TestCase):
    def test_level_crossing_interpolates(self):
        f = np.array([0.0, 0.1, 0.2, 0.3])
        m = np.array([1.0, 0.8, 0.4, 0.2])
        self.assertAlmostEqual(mtf_level_crossing(f, m, 0.5), 0.175)


if __name__ == "__main__":
    unittest.main()
