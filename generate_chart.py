"""Generate a measured, editable Westin ISO12233:2000 reconstruction."""
import argparse
from functools import lru_cache
import json
from pathlib import Path

import drawsvg as draw
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image
import pymupdf

ROOT = Path(__file__).resolve().parent


def draw_primitive(shape, style):
    """Build a parameterized shape, with coordinates relative to its placement."""
    kind = shape["kind"]
    if kind == "rectangle":
        return draw.Rectangle(0, 0, shape["width"], shape["height"], **style)
    if kind in ("polygon", "polyline"):
        coords = [v for xy in shape["vertices"] for v in xy]
        return draw.Lines(*coords, close=kind == "polygon", **style)
    if kind != "contour":
        raise ValueError(f"Unknown primitive kind {kind}")
    path = draw.Path(**style)
    for contour in shape["contours"]:
        path.M(*contour["start"])
        for segment in contour["segments"]:
            getattr(path, segment[0])(*segment[1:])
        if contour["closed"]:
            path.Z()
    return path


@lru_cache(maxsize=1)
def font():
    return TTFont(ROOT / "fonts/LiberationSans-Regular.ttf")


@lru_cache(maxsize=256)
def glyph_path(character):
    face = font()
    glyph_name = face.getBestCmap()[ord(character)]
    glyphs = face.getGlyphSet()
    pen = SVGPathPen(glyphs)
    glyphs[glyph_name].draw(pen)
    return pen.getCommands(), face["hmtx"][glyph_name][0]


def draw_label(label):
    """Open-font outlines make labels portable, without system font fallback."""
    scale = label["size"] / font()["head"].unitsPerEm
    group = draw.Group(transform=f"translate({label['x']} {label['y']}) scale({scale} {-scale})",
                       data_role="label", aria_label=label["text"])
    offset = 0
    for character in label["text"]:
        commands, advance = glyph_path(character)
        if commands:
            group.append(draw.Path(d=commands, transform=f"translate({offset} 0)", fill=label["fill"]))
        offset += advance
    return group


def build_chart(model=None, labels=True):
    if model is None:
        model = json.loads((ROOT / "chart_measurements.json").read_text())
    drawing = draw.Drawing(model["width"], model["height"], origin=(0, 0))
    # SVG user coordinates match PDF points; explicit units preserve print size.
    drawing.set_render_size(f"{model['width']}pt", f"{model['height']}pt")
    drawing.append_title("ISO12233:2000 - measured reconstruction of Stephen H. Westin's chart")
    drawing.append(draw.Raw("<desc>Based on Westin/Cornell (2004). "
                            "Measured geometry; Liberation Sans labels; printing footer removed. "
                            "Not certified as ISO-compliant.</desc>"))
    for component in model["components"]:
        group = draw.Group(id=component["id"])
        for instance in component["instances"]:
            x, y = instance["origin"]
            placement = draw.Group(transform=f"translate({x} {y})", data_source_id=instance["id"])
            placement.append(draw_primitive(model["primitives"][instance["primitive"]],
                                            model["styles"][instance["style"]]))
            group.append(placement)
        if labels:
            for label in component["labels"]:
                group.append(draw_label(label))
        drawing.append(group)
    return drawing


def render_svg(svg, width, supersample=2):
    """Rasterize vectors with bounded supersampling, then Lanczos reduction."""
    document = pymupdf.open(stream=svg.encode(), filetype="svg")
    page = document[0]
    height = round(width * page.rect.height / page.rect.width)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(width*supersample/page.rect.width,
                                                  height*supersample/page.rect.height), alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/iso12233.svg")
    parser.add_argument("--png", type=Path)
    parser.add_argument("--width", type=int, default=8192)
    args = parser.parse_args()
    if args.width < 32:
        parser.error("width must be at least 32")
    svg = build_chart().as_svg()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        render_svg(svg, args.width).save(args.png)
    print(f"Generated {args.output}")


if __name__ == "__main__":
    main()
