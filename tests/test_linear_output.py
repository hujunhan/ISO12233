"""Independent numerical checks and reference-readiness regression tests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from iso12233.generate_chart import ROOT, build_chart, ideal_neutral_chart, chart_availability
from iso12233.linear_output import render_linear_svg, save_srgb_preview, linear_to_srgb

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="100pt" height="61pt" viewBox="0 0 100 61"><rect width="100" height="61" fill="white"/><path d="M 0 0 L 61 0 L 39 61 L 0 61 Z" fill="black"/></svg>'


class LinearOutputTests(unittest.TestCase):
    def test_tile_error_is_bounded_and_preserves_area(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/"a.npy", Path(folder)/"b.npy"
            stats = render_linear_svg(SVG, a, 320, tile_rows=7)
            render_linear_svg(SVG, b, 320, tile_rows=1000)
            first, second = np.load(a), np.load(b)
            self.assertEqual(first.shape, (195, 320))
            self.assertEqual(first.dtype, np.float32)
            # MuPDF's clipped polygon antialiasing is not exactly invariant.
            # This fixture-specific tolerance is explicit in the published report.
            error = np.abs(first-second)
            self.assertLess(float(error.max()), 0.02)
            self.assertLess(float(error.mean()), 2e-5)
            # The independently specified trapezoid covers exactly half the canvas.
            self.assertLess(abs(float(first.mean()) - 0.5), 0.002)
            self.assertEqual(float(first.min()), 0.0)
            self.assertEqual(float(first.max()), 1.0)
            self.assertFalse(stats["gamma_applied"])

    def test_linear_average_is_encoded_after_averaging(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/"half.npy", Path(folder)/"preview.png"
            np.save(source, np.array([[0.0, 0.5, 1.0]], dtype=np.float32))
            save_srgb_preview(source, target)
            with Image.open(target) as image:
                self.assertEqual(np.asarray(image).ravel().tolist(), [0, 188, 255])
            self.assertAlmostEqual(float(linear_to_srgb([0.18])[0]), 0.461356, places=5)

    def test_neutralization_preserves_geometry_without_changing_default(self):
        baseline = build_chart().as_svg()
        neutral = ideal_neutral_chart()
        self.assertEqual(baseline, build_chart().as_svg())
        a, b = ET.fromstring(baseline), ET.fromstring(neutral)
        self.assertEqual(a.get("viewBox"), b.get("viewBox"))
        def geometry(root):
            ignored = {"fill", "stroke", "aria-label"}
            return [(e.tag, {k:v for k,v in e.attrib.items() if k not in ignored})
                    for e in root.iter()]
        self.assertEqual(geometry(a), geometry(b))
        self.assertNotIn("#272525", neutral)

    def test_modern_chart_catalog_keeps_unverified_details(self):
        for entry in chart_availability().values():
            self.assertEqual(entry["status"], "available_public_reconstruction")
            self.assertTrue(entry["unverified_standard_details"])

    def test_legacy_cli_writes_self_describing_npy(self):
        with tempfile.TemporaryDirectory() as folder:
            svg = Path(folder)/"chart.svg"
            data = Path(folder)/"chart.npy"
            preview = Path(folder)/"linear.png"
            subprocess.run([sys.executable, "-m","iso12233.generate_chart",
                            "--output", str(svg), "--linear", str(data),
                            "--linear-preview", str(preview), "--width", "320"],
                           check=True, capture_output=True)
            meta = json.loads(data.with_suffix(".json").read_text())
            self.assertEqual(np.load(data).shape, (194, 320))
            self.assertFalse(meta["calibrated_from_reference"])
            self.assertEqual(meta["reflectance_assumptions"], {"black":0.0,"white":1.0})
            self.assertEqual(meta["preview_transfer"], "sRGB")
            self.assertEqual(svg.read_text(), build_chart().as_svg())

    def test_invalid_outputs_are_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"chart.svg"
            for options in (["--linear-preview", str(Path(folder)/"preview.png")],
                            ["--linear", str(Path(folder)/"bad.raw")],
                            ["--linear", str(Path(folder)/"same.npy"),
                             "--metadata", str(Path(folder)/"same.npy")]):
                result = subprocess.run([sys.executable,"-m","iso12233.generate_chart",
                                         "--output",str(target),*options],capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
