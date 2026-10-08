"""Independently compare drawsvg geometry, raster output, and Westin PDF."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw
import pymupdf
from scipy.spatial import cKDTree
from svgpathtools import CubicBezier, Line, parse_path

from generate_chart import ROOT, build_chart, render_svg
from measure_chart import HEIGHT, NS, WIDTH, chart_paths


def segment_vectors(path, origin=0j):
    """Compare independent line/cubic coordinates, insensitive to traversal."""
    vectors = []
    for segment in path:
        if isinstance(segment, Line):
            if abs(segment.end-segment.start) < 1e-8:
                continue
            points = [segment.start+origin, segment.end+origin]
        elif isinstance(segment, CubicBezier):
            points = [segment.start+origin, segment.control1+origin,
                      segment.control2+origin, segment.end+origin]
        else:
            raise ValueError(type(segment))
        forward = tuple(v for p in points for v in (p.real, p.imag))
        reverse = tuple(v for p in reversed(points) for v in (p.real, p.imag))
        # Arithmetic in relative SVG commands introduces ~1e-12 pt noise;
        # use rounded keys so equal-x segments do not swap correspondence.
        vectors.append(min((forward, reverse), key=lambda v: tuple(round(x,6) for x in v)))
    return sorted(vectors, key=lambda v: (len(v), *(round(x,6) for x in v)))


def element_path(element):
    if element.tag == NS + "path":
        return parse_path(element.get("d"))
    if element.tag == NS + "rect":
        x, y, w, h = [float(element.get(k, 0)) for k in ("x", "y", "width", "height")]
        return parse_path(f"M{x},{y}h{w}v{h}h{-w}Z")
    raise ValueError(f"Unexpected generated shape {element.tag}")


def geometry_report(reference, generated):
    generated_shapes = {g.get("data-source-id"): g for g in generated.iter(NS+"g")
                        if g.get("data-source-id")}
    result, maximum, total = [], 0.0, 0
    for group in reference.findall(NS+"g"):
        name = group.get("id")
        if name == "credit":
            continue
        worst, bounds = 0.0, []
        paths = list(chart_paths(group))
        for i, source in paths:
            shape_id = f"{name}/shape-{i:04}"
            placement = generated_shapes.pop(shape_id)
            x, y = [float(n) for n in re.findall(r"[-+]?\d*\.?\d+", placement.get("transform"))]
            actual_element = list(placement)[0]
            expected_path = parse_path(source.get("d"))
            expected = segment_vectors(expected_path)
            actual = segment_vectors(element_path(actual_element), complex(x, y))
            if len(actual) != len(expected) or any(len(a) != len(b) for a, b in zip(actual, expected)):
                raise AssertionError(f"Segment structure differs: {shape_id}")
            delta = max((max(abs(a-b) for a, b in zip(av, ev))
                         for av, ev in zip(actual, expected)), default=0)
            worst = max(worst, delta)
            for attribute, default in [("fill", "black"), ("stroke", "none"),
                                       ("stroke-width", "1"), ("stroke-miterlimit", "4")]:
                a = actual_element.get(attribute, default)
                b = source.get(attribute, default)
                if a != b:
                    raise AssertionError(f"Style differs: {shape_id}/{attribute}: {a} vs {b}")
            bounds.append(expected_path.bbox())
        maximum = max(maximum, worst)
        total += len(paths)
        result.append({"component": name, "shape_count": len(paths),
                       "max_coordinate_error_pt": worst,
                       "bounds_pt": [min(b[0] for b in bounds), min(b[2] for b in bounds),
                                     max(b[1] for b in bounds), max(b[3] for b in bounds)]})
    if generated_shapes:
        raise AssertionError(f"Unexpected generated shapes: {list(generated_shapes)}")
    if maximum > 0.005:
        raise AssertionError(f"Geometry error {maximum} pt exceeds 0.005 pt")
    return {"shape_count": total, "max_coordinate_error_pt": maximum, "components": result}


def without_labels(root, source=False):
    root = copy.deepcopy(root)
    # Drop Adobe metadata, embedded fonts and entities; retain graphical groups.
    if source:
        for child in list(root):
            if child.tag != NS+"g" or child.get("id") == "credit":
                root.remove(child)
    for parent in root.iter():
        for child in list(parent):
            if child.tag == NS+"text" or child.get("data-role") == "label":
                parent.remove(child)
    root.set("width", str(WIDTH))
    root.set("height", str(HEIGHT))
    root.set("viewBox", f"0 0 {WIDTH} {HEIGHT}")
    return ET.tostring(root, encoding="unicode")


def normalize_layer(name):
    return re.sub("[^a-z0-9]", "", name.replace("_x0022_", '"').replace("_x002F_", "/").lower())


def pdf_crosscheck(pdf_path, reference):
    if not pdf_path.exists():
        return {"status": "not_run", "reason": "PDF reference not available"}
    page = pymupdf.open(pdf_path)[0]
    drawings = page.get_drawings()
    frame = drawings[0]["rect"]
    translation = np.array([frame.x0, frame.y0])
    pdf_groups = {}
    for drawing in drawings:
        name = normalize_layer(drawing["layer"])
        group = pdf_groups.setdefault(name, {"count": 0, "vertices": []})
        group["count"] += 1
        for item in drawing["items"]:
            if item[0] in ("l", "c"):
                group["vertices"].extend([[p.x, p.y] for p in item[1:]])
            elif item[0] == "re":
                r = item[1]
                group["vertices"].extend([[r.x0,r.y0],[r.x1,r.y0],[r.x1,r.y1],[r.x0,r.y1]])
    results = []
    for svg_group in reference.findall(NS+"g"):
        if svg_group.get("id") == "credit":
            continue
        name = normalize_layer(svg_group.get("id"))
        counterpart = pdf_groups.get(name)
        if counterpart is None:
            results.append({"component": svg_group.get("id"), "status": "no_matching_pdf_layer"})
            continue
        svg_vertices = []
        paths = list(chart_paths(svg_group))
        for _, p in paths:
            for s in parse_path(p.get("d")):
                points = [s.start, s.end]
                if isinstance(s, CubicBezier):
                    points += [s.control1, s.control2]
                svg_vertices.extend([[z.real, z.imag] for z in points])
        a = np.asarray(svg_vertices)
        b = np.asarray(counterpart["vertices"]) - translation
        forward = cKDTree(b).query(a)[0]
        backward = cKDTree(a).query(b)[0]
        results.append({"component": svg_group.get("id"), "svg_shape_count": len(paths),
                        "pdf_shape_count": counterpart["count"],
                        "max_bidirectional_vertex_distance_pt": float(max(forward.max(),backward.max()))})
    return {"status": "measured", "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
            "pdf_translation_pt": translation.tolist(),
            "note": "Vertex/control-point comparison, not a compliance or contour-distance test. "
                    "SVG is authoritative when source editions differ; PDF uses CMYK colors.",
            "components": results}


def validate(reference_path, output, widths=(2048, 8192)):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    reference = ET.parse(reference_path).getroot()
    full_svg = build_chart().as_svg()
    generated = ET.fromstring(full_svg)
    report = {"reference_sha256": hashlib.sha256(Path(reference_path).read_bytes()).hexdigest(),
              "geometry": geometry_report(reference, generated), "raster": []}
    source_svg = without_labels(reference, source=True)
    generated_svg = without_labels(generated)
    for width in widths:
        a = render_svg(source_svg, width)
        b = render_svg(generated_svg, width)
        av, bv = np.asarray(a).astype(np.int16), np.asarray(b).astype(np.int16)
        delta = np.abs(av-bv).astype(np.uint8)
        changed = np.any(delta != 0, axis=2)
        stats = {"width": width, "height": a.height,
                 "mean_abs_error_8bit": float(delta.mean()), "max_abs_error_8bit": int(delta.max()),
                 "changed_pixels": int(changed.sum()), "compared_pixels": int(changed.size)}
        # Raster engines can respond slightly differently to equivalent path order.
        if stats["mean_abs_error_8bit"] > 1.0:
            raise AssertionError(f"Raster mismatch: {stats}")
        report["raster"].append(stats)
        Image.fromarray(np.minimum(delta.astype(np.uint16)*16,255).astype(np.uint8)).save(
            output/f"difference-{width}.png")
        if width == 2048:
            a.save(output/"reference-geometry.png")
            b.save(output/"generated-geometry.png")
            Image.blend(a,b,0.5).save(output/"overlay-2048.png")
        if width == 8192:
            regions = [
                ("Center zone plate", (530,309,592,372)),
                ("High frequency vertical wedge", (620,140,650,312)),
                ("Bottom sweep detail", (520,505,620,558)),
                ("Upper-left corner crossing", (110,170,180,230)),
                ("Lower-right corner crossing", (905,455,975,505)),
                ("Diagonal sweep", (342,139,420,218)),
            ]
            sheet = Image.new("RGB",(850,330*len(regions)),"white")
            pen = ImageDraw.Draw(sheet)
            for row,(name,box) in enumerate(regions):
                scaled = tuple(round(v*width/WIDTH) for v in box)
                for column,image in enumerate((a,b)):
                    crop = image.crop(scaled)
                    crop.thumbnail((415,300),Image.Resampling.LANCZOS)
                    sheet.paste(crop,(column*425,row*330+25))
                    pen.text((column*425+5,row*330+5),
                             f"{'Reference' if column==0 else 'Generated'}: {name}",fill="black")
            sheet.save(output/"detail-comparison.png")
        print(f"Raster {width}: {stats}", flush=True)
        del a,b,av,bv,delta,changed
    model = json.loads((ROOT/"chart_measurements.json").read_text())
    report["labels"] = {"count": sum(len(c["labels"]) for c in model["components"]),
                         "policy": "Measured content, baseline and size; Liberation Sans outlines. "
                                   "Glyph shapes differ and are excluded from geometry raster comparison."}
    report["pdf_crosscheck"] = pdf_crosscheck(Path(reference_path).with_suffix(".pdf"),reference)
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference",type=Path,default=ROOT/"references/ISO_12233-reschart.svg")
    parser.add_argument("--output",type=Path,default=ROOT/"output/validation")
    args = parser.parse_args()
    validate(args.reference,args.output)
