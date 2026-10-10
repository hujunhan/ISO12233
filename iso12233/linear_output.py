"""Bounded-memory export of neutral vector targets in a linear numeric domain.

SVG grayscale paint values are interpreted as linear intensities, NOT decoded
from sRGB. MuPDF rasterization has 8-bit coverage precision. Analytic sine-wave
patterns must be evaluated directly in float, rather than through this backend.
"""
import numpy as np
from PIL import Image
import pymupdf


def linear_to_srgb(values):
    values = np.asarray(values, dtype=np.float32)
    return np.where(values <= 0.0031308, 12.92 * values,
                    1.055 * np.maximum(values, 0) ** (1 / 2.4) - 0.055)


def render_linear_svg(svg, destination, width, supersample=4, tile_rows=32):
    """Write grayscale float32 NPY; average subpixels before display encoding.

    The caller must provide neutral paint whose numeric values represent linear
    intensities. This does not infer physical reflectance from arbitrary artwork.
    Returned statistics avoid allocating a second full-size array.
    """
    if width < 32 or supersample < 1 or tile_rows < 1:
        raise ValueError("width >= 32, supersample >= 1 and tile_rows >= 1 required")
    with pymupdf.open(stream=svg.encode(), filetype="svg") as document:
        page = document[0]
        display_list = page.get_displaylist()
        height = round(width * page.rect.height / page.rect.width)
        if height < 1:
            raise ValueError("SVG aspect ratio produces an empty image")
        destination.parent.mkdir(parents=True, exist_ok=True)
        output = np.lib.format.open_memmap(destination, mode="w+", dtype=np.float32,
                                           shape=(height, width))
        sx = width * supersample / page.rect.width
        sy = height * supersample / page.rect.height
        minimum, maximum = 1.0, 0.0
        total = 0.0
        try:
            for y0 in range(0, height, tile_rows):
                y1 = min(height, y0 + tile_rows)
                # Halo prevents clipping/rounding at the tile boundary.
                clip = pymupdf.Rect(0, max(0, y0 * supersample - 2) / sy,
                                   page.rect.width,
                                   min(height * supersample, y1 * supersample + 2) / sy)
                pixmap = display_list.get_pixmap(matrix=pymupdf.Matrix(sx, sy), clip=clip,
                                        colorspace=pymupdf.csGRAY, alpha=False)
                samples = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height, pixmap.width)
                top = y0 * supersample - pixmap.irect[1]
                left = -pixmap.irect[0]
                samples = samples[top:top + (y1-y0)*supersample,
                                  left:left + width*supersample]
                block = samples.reshape(y1-y0, supersample, width, supersample).mean(
                    axis=(1, 3), dtype=np.float32) / 255
                output[y0:y1] = block
                minimum = min(minimum, float(block.min()))
                maximum = max(maximum, float(block.max()))
                total += float(block.sum(dtype=np.float64))
            output.flush()
        finally:
            del output
    return {"width": width, "height": height, "dtype": "float32",
            "min": minimum, "max": maximum, "mean": total / (width * height),
            "supersample": supersample, "tile_rows": tile_rows,
            "sampling": "box average in linear domain",
            "vector_coverage_precision": "8-bit per subpixel before averaging",
            "gamma_applied": False}


def save_srgb_preview(linear_path, destination, tile_rows=32):
    """Display-only grayscale PNG; keep the linear NPY as the simulation input."""
    values = np.load(linear_path, mmap_mode="r")
    if values.ndim != 2 or values.dtype != np.float32:
        raise ValueError("Expected a two-dimensional float32 NPY")
    height, width = values.shape
    image = Image.new("L", (width, height))
    for y0 in range(0, height, tile_rows):
        block = values[y0:min(height, y0 + tile_rows)]
        encoded = np.rint(np.clip(linear_to_srgb(block), 0, 1) * 255).astype(np.uint8)
        image.paste(Image.fromarray(encoded), (0, y0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
