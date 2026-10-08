"""Measure Westin's SVG into editable primitives and component placements."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

from svgpathtools import CubicBezier, Line, parse_path

NS = "{http://www.w3.org/2000/svg}"
ROOT = Path(__file__).resolve().parent
SOURCE_URL = "https://www.graphics.cornell.edu/~westin/misc/ISO_12233-reschart.svg"
WIDTH, HEIGHT = 1121.273, 680.314


def chart_paths(group):
    """Skip two nonpainting Illustrator layout boxes, including the footer."""
    for i, path in enumerate(group.iter(NS + "path")):
        if path.get("fill") == "none" and path.get("stroke", "none") == "none":
            continue
        yield i, path


def point(z):
    return [round(z.real, 9), round(z.imag, 9)]


def primitive(path_text):
    path = parse_path(path_text)
    origin = path[0].start
    parts = path.continuous_subpaths()
    if len(parts) == 1 and all(isinstance(s, Line) for s in path):
        vertices = [path[0].start] + [s.end for s in path]
        closed = abs(vertices[-1] - vertices[0]) < 1e-8
        if closed:
            vertices.pop()
        # Illustrator sometimes repeats the closing point before 'z'.
        vertices = [p for i, p in enumerate(vertices)
                    if i == 0 or abs(p - vertices[i - 1]) > 1e-8]
        if len(vertices) == 4 and closed:
            xs, ys = [p.real for p in vertices], [p.imag for p in vertices]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            corners = [complex(x0, y0), complex(x1, y0),
                       complex(x1, y1), complex(x0, y1)]
            if all(min(abs(p - c) for c in corners) < 1e-8 for p in vertices):
                return [x0, y0], {"kind": "rectangle", "width": round(x1-x0, 9),
                                 "height": round(y1-y0, 9)}
        return point(origin), {"kind": "polygon" if closed else "polyline",
                               "vertices": [point(p-origin) for p in vertices]}
    contours = []
    for part in parts:
        segments = []
        for s in part:
            if isinstance(s, Line):
                segments.append(["L", *point(s.end-origin)])
            elif isinstance(s, CubicBezier):
                segments.append(["C", *point(s.control1-origin),
                                 *point(s.control2-origin), *point(s.end-origin)])
            else:
                raise ValueError(f"Unsupported measured segment: {type(s)}")
        contours.append({"start": point(part[0].start-origin),
                         "segments": segments, "closed": part.isclosed()})
    return point(origin), {"kind": "contour", "contours": contours}


def measure(source):
    source = Path(source)
    root = ET.parse(source).getroot()
    catalog, catalog_keys, components, styles = [], {}, [], []
    for group in root.findall(NS + "g"):
        name = group.get("id")
        if name == "credit":
            continue
        component = {"id": name, "instances": [], "labels": []}
        for i, path in chart_paths(group):
            origin, shape = primitive(path.get("d"))
            key = json.dumps(shape, sort_keys=True)
            if key not in catalog_keys:
                catalog_keys[key] = len(catalog)
                catalog.append(shape)
            style = {k.replace("-", "_"): v for k, v in path.attrib.items() if k != "d"}
            style.setdefault("fill", "black")  # SVG's default, not #272525.
            if style not in styles:
                styles.append(style)
            component["instances"].append({"id": f"{name}/shape-{i:04}",
                                          "origin": origin, "primitive": catalog_keys[key],
                                          "style": styles.index(style)})
        for text in group.iter(NS + "text"):
            values = [float(n) for n in re.findall(r"[-+]?\d*\.?\d+", text.get("transform", ""))]
            if len(values) != 6 or values[:4] != [1, 0, 0, 1]:
                raise ValueError(f"Unexpected text transform: {text.attrib}")
            for span in text.findall(NS + "tspan"):
                x, y = values[4] + float(span.get("x", 0)), values[5] + float(span.get("y", 0))
                if y > HEIGHT:  # Printing form is in Text_at_top, not credit.
                    continue
                component["labels"].append({"text": span.text or "", "x": x, "y": y,
                                            "size": float(span.get("font-size")),
                                            "fill": span.get("fill", "black"),
                                            "source_font": span.get("font-family")})
        components.append(component)
    return {"source": {"url": SOURCE_URL, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "copyright": "Copyright (c) 2004 Cornell University Program of Computer Graphics",
                       "original_viewbox": root.get("viewBox")},
            "units": "PDF points (1/72 inch)", "width": WIDTH, "height": HEIGHT,
            "font": "Liberation Sans Regular 2.1.5",
            "styles": styles, "primitives": catalog, "components": components}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=ROOT / "references/ISO_12233-reschart.svg")
    parser.add_argument("--output", type=Path, default=ROOT / "chart_measurements.json")
    args = parser.parse_args()
    model = measure(args.reference)
    args.output.write_text(json.dumps(model, indent=2) + "\n")
    counts = Counter(p["kind"] for p in model["primitives"])
    print(f"Measured {len(model['components'])} components, "
          f"{sum(len(c['instances']) for c in model['components'])} shapes; "
          f"{len(model['primitives'])} reusable primitives: {dict(counts)}")


if __name__ == "__main__":
    main()
