"""Checks of independent frequency/reflectance expectations, not ISO certification."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from iso12233.modern_charts import Scene, build_scene, build_svg, sample_scene, raster_blocks, add_wedge, add_sweep
from iso12233.generate_chart import ROOT


def sample(scene,x,y):
    return float(sample_scene(scene,np.array([x]),np.array([y]))[0,0])


class ModernChartTests(unittest.TestCase):
    def test_esfr_nine_targets_and_linear_four_to_one(self):
        scene=build_scene("esfr2024")
        edges=[s for s in scene.shapes if s.get("role")=="esfr_edge"]
        self.assertEqual(len(edges),36)
        self.assertEqual(len(set(tuple(s["star_center"]) for s in edges)),9)
        def at(theta):
            a=math.radians(theta)
            return sample(scene,170+15*math.sin(a),120-15*math.cos(a))
        self.assertAlmostEqual(at(20),0.05,places=7)
        self.assertAlmostEqual(at(70),0.20,places=7)
        self.assertAlmostEqual(at(70)/at(20),4,places=6)
        patches=[s for s in scene.shapes if s.get("role")=="oecf"]
        self.assertEqual(sorted(s["patch_index"] for s in patches),list(range(1,17)))
        values=sorted(s["value"] for s in patches)
        self.assertAlmostEqual(values[-1]/values[0],20)

    def test_sine_wave_fundamental_and_reflectance(self):
        scene=Scene("test",290,270,0.18,0.009,{})
        scene.add("star",[20,10,270,260],center=[145,135],radius=125,inner_radius=12.5,
                  cycles=144,phase=0,low=0.009,high=0.9,background=0.18)
        theta=np.arange(2048)*2*math.pi/2048
        signal=np.array([sample(scene,145+90*math.cos(a),135+90*math.sin(a)) for a in theta])
        spectrum=np.abs(np.fft.rfft(signal-signal.mean()))
        self.assertEqual(int(spectrum[1:].argmax()+1),144)
        self.assertAlmostEqual(signal.mean(),(0.9+0.009)/2,places=7)
        self.assertAlmostEqual(spectrum[144]*2/len(signal),(0.9-0.009)/2,places=7)
        self.assertLess(float(np.max(np.abs(signal-(0.4545+0.4455*np.cos(144*theta))))),1e-6)

    def test_gray_patches_and_single_grid_alternatives(self):
        for layout,count,width in (("single",1,290),("grid",9,1070)):
            scene=build_scene("ssfr",layout,72)
            stars=[s for s in scene.shapes if s["kind"]=="star"]
            patches=[s for s in scene.shapes if s.get("role")=="linearization_patch"]
            self.assertEqual(len(stars),count)
            self.assertEqual(len(patches),16*count)
            self.assertEqual(scene.width,width)
            self.assertTrue(all(s["cycles"]==72 for s in stars))
            values=[s["value"] for s in patches[:16]]
            np.testing.assert_allclose(np.diff(values),-(0.9-0.009)/15)
            self.assertAlmostEqual(stars[0]["high"]/stars[0]["low"],100)

    def test_wedge_five_lines_and_active_height_normalization(self):
        scene=Scene("wedge",100,20,0.8,0.01,{})
        add_wedge(scene,[0,10],0,96.55,200,2500,200,0.01,0.8,False)
        for f in (500,1000,2000):
            s=96.55*(f-200)/2300
            expected_width=200/f
            us=np.linspace(-5*expected_width,5*expected_width,10001)
            values=sample_scene(scene,np.array([s]),us+10)[:,0]
            black=values<0.1
            starts=np.flatnonzero(np.diff(black.astype(int))==1)
            ends=np.flatnonzero(np.diff(black.astype(int))==-1)
            self.assertEqual(len(starts),5)
            self.assertEqual(len(ends),5)
            widths=(ends-starts)*(us[1]-us[0])
            np.testing.assert_allclose(widths,expected_width,atol=expected_width*0.003)

    def test_sweep_uses_integrated_frequency(self):
        scene=Scene("sweep",100,10,0.8,0.01,{})
        add_sweep(scene,[0,5],0,91,200,1500,0.01,0.8)
        a,b=200/400,1300/(800*91)
        first_end=1/(a+math.sqrt(a*a+2*b))  # independent solution of phase=1/2
        self.assertLess(sample(scene,first_end-0.0001,5),0.1)
        self.assertGreater(sample(scene,first_end+0.0001,5),0.7)

    def test_analytic_sampling_is_exactly_tile_invariant(self):
        for name in ("cipa","esfr2024","ssfr"):
            scene=build_scene(name)
            a=np.concatenate([block for _,block in raster_blocks(scene,128,2,7)])
            b=np.concatenate([block for _,block in raster_blocks(scene,128,2,1000)])
            np.testing.assert_array_equal(a,b,err_msg=name)
            self.assertGreaterEqual(float(a.min()),0)
            self.assertLessEqual(float(a.max()),1)

    def test_svg_is_self_contained_with_physical_units(self):
        ns="{http://www.w3.org/2000/svg}"
        for name in ("cipa","esfr2024","ssfr"):
            svg=build_svg(build_scene(name),256,2)
            root=ET.fromstring(svg)
            self.assertTrue(root.attrib["width"].endswith("mm"))
            metadata=json.loads(root.find(ns+"metadata").text)
            self.assertFalse(metadata["standard_certification"])
            for elem in root.iter():
                for key,value in elem.attrib.items():
                    if key.endswith("href"):
                        self.assertTrue(value.startswith(("#","data:")))
            if name=="ssfr":
                self.assertEqual(len(list(root.iter(ns+"image"))),1)
                self.assertEqual(len(list(root.iter(ns+"use"))),9)

    def test_cli_writes_full_metadata_and_linear_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            result=subprocess.run([sys.executable,"-m","iso12233.generate_chart","--chart","esfr2024",
                "--output",str(base/"chart.svg"),"--linear",str(base/"chart.npy"),
                "--png",str(base/"chart.png"),"--width","320"],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=np.load(base/"chart.npy")
            self.assertEqual(data.shape,(226,320))
            self.assertEqual(data.dtype,np.float32)
            meta=json.loads((base/"chart.json").read_text())
            self.assertFalse(meta["standard_certification"])
            self.assertFalse(meta["sampling"]["gamma_applied"])
            self.assertEqual(meta["active_area_mm"],[20,20,300,200])
            self.assertIn("selected",meta["profile"]["provenance"])


if __name__=="__main__": unittest.main()
