"""Regression tests for independent geometry, font and raster behavior."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from iso12233.generate_chart import ROOT, build_chart, render_svg
from iso12233.measure_chart import NS, measure
from iso12233.validate_chart import geometry_report


class ChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads((ROOT/"data/iso2000_measurements.json").read_text())

    def test_portable_generation_and_open_font_outlines(self):
        first = build_chart(self.model).as_svg()
        self.assertEqual(first,build_chart(self.model).as_svg())
        root = ET.fromstring(first)
        self.assertEqual(root.get("width"),"1121.273pt")
        self.assertEqual(root.get("height"),"680.314pt")
        self.assertEqual(len(list(root.iter(NS+"image"))),0)
        self.assertNotIn("@font-face",first)
        labels = [g.get("aria-label") for g in root.iter(NS+"g") if g.get("data-role")=="label"]
        expected = [label["text"] for c in self.model["components"] for label in c["labels"]]
        self.assertEqual(labels,expected)
        self.assertEqual(len(labels),159)
        self.assertFalse(any("Printed by" in label for label in labels))

    def test_aspect_ratio_and_png_dimensions(self):
        image = render_svg(build_chart(labels=False).as_svg(),320)
        self.assertEqual(image.size,(320,194))
        self.assertEqual(image.mode,"RGB")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"preview.png"
            image.save(path)
            self.assertGreater(path.stat().st_size,1000)

    @unittest.skipUnless((ROOT/"references/ISO_12233-reschart.svg").exists(),"Reference not downloaded")
    def test_independent_reference_geometry(self):
        reference = ET.parse(ROOT/"references/ISO_12233-reschart.svg").getroot()
        report = geometry_report(reference,ET.fromstring(build_chart().as_svg()))
        self.assertEqual(report["shape_count"],1154)
        self.assertLess(report["max_coordinate_error_pt"],1e-8)

    @unittest.skipUnless((ROOT/"references/ISO_12233-reschart.svg").exists(),"Reference not downloaded")
    def test_validator_rejects_changed_bar_width(self):
        broken = copy.deepcopy(self.model)
        broken["primitives"][0]["width"] += 0.1
        reference = ET.parse(ROOT/"references/ISO_12233-reschart.svg").getroot()
        with self.assertRaises(AssertionError):
            geometry_report(reference,ET.fromstring(build_chart(broken).as_svg()))

    @unittest.skipUnless((ROOT/"references/ISO_12233-reschart.svg").exists(),"Reference not downloaded")
    def test_measurements_reproduce_from_source(self):
        self.assertEqual(measure(ROOT/"references/ISO_12233-reschart.svg"),self.model)


if __name__ == "__main__":
    unittest.main()
