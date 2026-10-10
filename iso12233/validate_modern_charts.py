"""Measure public-reference reconstruction and sampling limits; no ISO certification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw
from iso12233.modern_charts import build_scene, raster_blocks, sample_scene, point

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def raster(scene, width, samples, rows=16):
    return np.concatenate([block for _, block in raster_blocks(scene, width, samples, rows)])


def validate(output):
    output.mkdir(parents=True, exist_ok=True)
    report = {
        'standard_certification': False,
        'purpose': 'Numerical sampling checks and approximate public-preview geometry comparison',
        'error_units': 'absolute linear reflectance (0 to 1)',
        'convergence_note': '16x16 samples are a numerical reference, not exact area integration. Comparisons use width 512; values do not bound all 8192-pixel errors.',
        'charts': {},
    }
    thumbs = []
    for name in ('cipa', 'esfr2024', 'ssfr'):
        scene = build_scene(name)
        exact_a, exact_b = raster(scene, 128, 4, 7), raster(scene, 128, 4, 1000)
        item = {'tile_invariant': bool(np.array_equal(exact_a, exact_b)), 'sampling_width': 512}
        if not item['tile_invariant']:
            raise AssertionError(f'Tile dependence: {name}')
        reference = raster(scene, 512, 16)
        item['convergence'] = {}
        for samples in (4, 8):
            error = np.abs(raster(scene, 512, samples) - reference)
            item['convergence'][str(samples)] = {
                'max_absolute_error': float(error.max()),
                'mean_absolute_error': float(error.mean()),
                'p99_absolute_error': float(np.percentile(error, 99)),
            }
        # Probe measurement patterns at the delivered resolution, without labels.
        # Fixed global coordinates preserve the generator's pixel integration grid.
        width, height = 8192, round(8192*scene.height/scene.width)
        probes = []
        if name == 'esfr2024':
            centers = [(170,110), (185,100), (170,45), (80,55)]
        elif name == 'ssfr':
            centers = [(157.5,135), (180,135), (230,135), (547.5,405)]
        else:
            centers = []
            for shape in scene.shapes:
                if shape['kind'] in ('wedge','sweep'):
                    centers.append(point(shape['origin'], shape['angle'], shape['length']*.65))
            centers = centers[:4] + centers[-4:]
        for cx, cy in centers:
            x0 = max(0,min(width-64,round(cx*width/scene.width)-32))
            y0 = max(0,min(height-64,round(cy*height/scene.height)-32))
            def probe(samples):
                xs=(np.arange(x0*samples,(x0+64)*samples)+.5)*scene.width/(width*samples)
                ys=(np.arange(y0*samples,(y0+64)*samples)+.5)*scene.height/(height*samples)
                return sample_scene(scene,xs,ys).reshape(64,samples,64,samples).mean(axis=(1,3),dtype=np.float32)
            target=probe(16)
            errors={}
            for samples in (4,8):
                difference=np.abs(probe(samples)-target)
                errors[str(samples)]={'maximum':float(difference.max()),'mean':float(difference.mean())}
            probes.append({'pixel_origin':[x0,y0],'size':[64,64],'errors_vs_16':errors})
        item['production_sampling_probes']={'width':width,'height':height,'labels_included':False,
            'note':'Selected measurement ROIs only, not a global error bound; 16x16 reference remains approximate.',
            'regions':probes}
        folder = ROOT / 'charts' / name
        metadata = json.loads((folder / 'metadata.json').read_text())
        array = np.load(ROOT / f'output/linear/{name}.npy', mmap_mode='r')
        if array.shape != (metadata['height'], metadata['width']) or array.dtype != np.float32:
            raise AssertionError(f'Array schema mismatch: {name}')
        minimum, maximum = 1., 0.
        for row in range(0, len(array), 128):
            block = array[row:row+128]
            if not np.isfinite(block).all():
                raise AssertionError(f'Non-finite values: {name}')
            minimum, maximum = min(minimum, float(block.min())), max(maximum, float(block.max()))
        if not 0 <= minimum <= maximum <= 1:
            raise AssertionError(f'Invalid reflectance range: {name}')
        for filename, expected in metadata['generator_sha256'].items():
            if digest(ROOT / filename) != expected:
                raise AssertionError(f'Generator differs from artifact metadata: {filename}')
        svg = ET.parse(folder / 'chart.svg').getroot()
        for element in svg.iter():
            for key, value in element.attrib.items():
                if key.endswith('href') and not value.startswith(('#', 'data:')):
                    raise AssertionError(f'External SVG asset: {name}')
        with Image.open(folder / 'preview-8192.png') as picture:
            if picture.size != (metadata['width'], metadata['height']):
                raise AssertionError(f'Preview dimensions: {name}')
            thumb = picture.convert('RGB')
            thumb.thumbnail((1100, 760))
        thumbs.append((name, thumb))
        item['production'] = {
            'shape': list(array.shape), 'dtype': str(array.dtype),
            'minimum': minimum, 'maximum': maximum,
            'generator_hashes_match': True,
            'sha256': {filename: digest(folder / filename) for filename in ('chart.svg', 'preview-8192.png', 'metadata.json')},
            'linear_npy_sha256': digest(ROOT / f'output/linear/{name}.npy'),
        }
        benchmark_path = ROOT / f'output/benchmarks/{name}.txt'
        benchmark = benchmark_path.read_text() if benchmark_path.exists() else ''
        for key, pattern in [('wall_seconds', r'([\d.]+) real'), ('maximum_resident_bytes', r'(\d+)\s+maximum resident set size'), ('peak_memory_footprint_bytes', r'(\d+)\s+peak memory footprint')]:
            found = re.search(pattern, benchmark)
            if found:
                item['production'][key] = float(found[1]) if key == 'wall_seconds' else int(found[1])
        report['charts'][name] = item
    refs = json.loads((ROOT / 'data/modern_references.json').read_text())
    anchors = refs['public_reference_measurements']['esfr2024']
    bounds = anchors['approximate_active_bounds_px']
    observed = np.asarray(anchors['observed_star_centers_px'], dtype=float)
    measured = (observed - bounds[:2]) * [300/(bounds[2]-bounds[0]), 200/(bounds[3]-bounds[1])] + [20, 20]
    generated = np.asarray(build_scene('esfr2024').profile['parameters']['star_centers'])
    distances = np.linalg.norm(measured-generated, axis=1)
    report['esfr_public_preview_anchors'] = {
        'source': anchors['file'], 'active_bounds_px': bounds,
        'measured_centers_mm': measured.tolist(), 'generated_centers_mm': generated.tolist(),
        'offset_distances_mm': distances.tolist(), 'maximum_mm': float(distances.max()),
        'caveat': 'Manual low-resolution preview measurements. Draft figure, approximate crop and pixel placement; not a standard tolerance test.',
    }
    canvas = Image.new('RGB', (1140, sum(im.height+55 for _, im in thumbs)+20), 'white')
    drawing = ImageDraw.Draw(canvas)
    y = 15
    for name, im in thumbs:
        drawing.text((20,y), f'{name} - public-reference reconstruction', fill='black')
        canvas.paste(im, (20,y+30))
        y += im.height+55
    canvas.save(output/'contact-sheet.png')
    destination = output/'report.json'
    destination.write_text(json.dumps(report, indent=2)+'\n')
    print(destination)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'output/validation/modern')
    args = parser.parse_args()
    validate(args.output)
