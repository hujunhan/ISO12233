"""Generate legacy and public-reference ISO12233 chart reconstructions."""
import argparse
from functools import lru_cache
import json
from pathlib import Path

import drawsvg as draw
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image
import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def chart_availability():
    return json.loads((ROOT / "data/modern_references.json").read_text())["charts"]


def ideal_neutral_chart():
    """Legacy geometry with explicitly assumed black=0 and white=1 reflectance.

    Westin's near-black colored artwork is not a reflectance calibration.
    """
    model = json.loads((ROOT / "data/iso2000_measurements.json").read_text())
    for style in model["styles"]:
        for key in ("fill", "stroke"):
            if key in style and style[key] != "none":
                style[key] = "white" if style[key].lower() in ("white", "#ffffff") else "black"
    for component in model["components"]:
        for label in component["labels"]:
            label["fill"] = "black"
    return build_chart(model).as_svg()


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
    return TTFont(ROOT / "assets/fonts/LiberationSans-Regular.ttf")


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
        model = json.loads((ROOT / "data/iso2000_measurements.json").read_text())
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



def generate_modern(args):
    import hashlib
    import tempfile
    from iso12233.modern_charts import build_scene, build_svg, render_linear
    from iso12233.linear_output import save_srgb_preview
    scene = build_scene(args.chart, args.ssfr_layout or "grid", args.cycles or 144)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_svg(scene, args.width, args.supersample))
    statistics = None
    if args.linear or args.png:
        with tempfile.TemporaryDirectory(prefix="iso12233-") as folder:
            data_path = args.linear or Path(folder)/"reflectance.npy"
            statistics = render_linear(scene, data_path, args.width, args.supersample)
            if args.png:
                save_srgb_preview(data_path, args.png)
            if args.linear_preview:
                save_srgb_preview(data_path, args.linear_preview)
    metadata = {"chart": args.chart, "reconstruction": "public-reference approximation",
                "standard_certification": False, "coordinate_unit": "mm",
                "canvas_mm": [scene.width,scene.height],
                "quantity": "spectrally neutral synthetic linear reflectance",
                "array_layout": "height,width", "preview_transfer": "sRGB",
                "width": args.width, "height": round(args.width*scene.height/scene.width),
                "profile": scene.profile, "shapes": scene.shapes,
                "labels": scene.labels, "sampling": statistics,
                "linear_file": str(args.linear) if args.linear else None,
                "svg_embedded_images": "Generated display previews only; do not decode as float ground truth",
                "generator_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                    for name in ("iso12233/modern_charts.py","data/modern_profiles.json","iso12233/generate_chart.py")}}
    if args.chart == "ssfr":
        star=next(s for s in scene.shapes if s["kind"]=="star")
        metadata["ssfr"]={"layout":args.ssfr_layout or "grid", "cycles":args.cycles or 144,
            "frequency_formula_cycles_per_mm":"cycles/(2*pi*radius_mm)",
            "max_unmasked_frequency_cycles_per_pixel":star["cycles"]/(2*3.141592653589793*
                star["inner_radius"]*args.width/scene.width),
            "svg_star_raster_width":max(32,round(2*star["radius"]*args.width/scene.width))}
    else:
        metadata["active_area_mm"]=[20,20,300,200]
        metadata["frequency_normalization_height_mm"]=200
    metadata_path = args.metadata or (args.linear.with_suffix(".json") if args.linear else args.output.with_suffix(".json"))
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata,indent=2)+"\n")
    print(f"Generated {args.chart}: {args.output}, {metadata_path}; public-reference reconstruction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart", choices=("iso2000", "cipa", "esfr2024", "ssfr"),
                        default="iso2000")
    parser.add_argument("--list-charts", action="store_true",
                        help="Show source readiness, including missing parameters")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--linear", type=Path, help="Write linear reflectance float32 NPY (suffix .npy)")
    parser.add_argument("--linear-preview", type=Path, help="Write sRGB preview of the NPY")
    parser.add_argument("--metadata", type=Path, help="Linear-output JSON (default: NPY path with .json)")
    parser.add_argument("--png", type=Path)
    parser.add_argument("--width", type=int, default=8192)
    parser.add_argument("--supersample", type=int, default=4,
                        help="Subpixel samples per axis for linear output (default 4)")
    parser.add_argument("--ssfr-layout", choices=("single", "grid"), default=None)
    parser.add_argument("--cycles", type=int, choices=(72,144), default=None)
    args = parser.parse_args()
    if args.width < 32 or args.supersample < 1:
        parser.error("width must be at least 32; supersample must be positive")
    if args.chart != "ssfr" and (args.ssfr_layout or args.cycles):
        parser.error("--ssfr-layout and --cycles apply only to ssfr")
    if args.output is None:
        filename = "iso12233" if args.chart == "iso2000" else args.chart
        args.output = ROOT / "output" / (filename + ".svg")
    availability = chart_availability()
    if args.list_charts:
        print("iso2000: available (measured Westin reconstruction)")
        for name, entry in availability.items():
            print(f"{name}: {entry['status']}")
            for detail in entry["unverified_standard_details"]:
                print(f"  Not verified: {detail}")
        return
    if args.linear_preview and not args.linear:
        parser.error("--linear-preview requires --linear")
    if args.chart == "iso2000" and args.metadata and not args.linear:
        parser.error("--metadata requires --linear for iso2000")
    if args.linear and args.linear.suffix.lower() != ".npy":
        parser.error("--linear output must have the .npy suffix")
    paths = [p.resolve() for p in (args.output, args.png, args.linear, args.linear_preview,
             args.metadata or (args.linear.with_suffix(".json") if args.linear else (args.output.with_suffix(".json") if args.chart != "iso2000" else None))) if p]
    if len(set(paths)) != len(paths):
        parser.error("Output paths must be distinct")
    if args.chart != "iso2000":
        generate_modern(args)
        return
    svg = build_chart().as_svg()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        render_svg(svg, args.width).save(args.png)
    if args.linear:
        from iso12233.linear_output import render_linear_svg, save_srgb_preview
        stats = render_linear_svg(ideal_neutral_chart(), args.linear, args.width, args.supersample)
        metadata = {"chart": "iso2000", "standard_certification": False,
                    "quantity": "assumed neutral reflectance",
                    "reflectance_assumptions": {"black": 0.0, "white": 1.0},
                    "calibrated_from_reference": False,
                    "source_artwork_colors_preserved": False,
                    "linear_file": str(args.linear), "array_layout": "height,width",
                    "active_picture_height_mm": 200,
                    "frequency_unit": "LW/PH of active inner picture height",
                    "outer_viewbox_pt": [0, 0, 1121.273, 680.314],
                    "preview_transfer": "sRGB" if args.linear_preview else None,
                    "sampling": stats}
        metadata_path = args.metadata or args.linear.with_suffix(".json")
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        if args.linear_preview:
            save_srgb_preview(args.linear, args.linear_preview)
        print(f"Generated {args.linear} and {metadata_path}")
    print(f"Generated {args.output}")


if __name__ == "__main__":
    main()
