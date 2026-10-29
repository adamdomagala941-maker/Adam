"""Conservative visual recognition of standard red GHS diamonds in PDF §2.2.

This is template matching, not a classifier derived from hazard statements.
Unrecognized/monochrome/low-resolution symbols remain unclassified. Callers must
retain the requirement to compare the result against the original SDS.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import fitz
import numpy as np
from PIL import Image
from scipy import ndimage

ASSETS = Path(__file__).resolve().parents[1] / "frontend" / "public" / "template"
MIN_SCORE = 0.91
MIN_MARGIN = 0.07


def _black_shape(rgb: np.ndarray) -> np.ndarray | None:
    """Normalize the black silhouette inside the red diamond, excluding border."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    interior = abs((xx - w / 2) / (w / 2)) + abs((yy - h / 2) / (h / 2)) < 0.82
    black = (rgb.max(axis=2) < 125) & interior
    ys, xs = np.nonzero(black)
    if len(xs) < 12:
        return None
    left, right, top, bottom = xs.min(), xs.max()+1, ys.min(), ys.max()+1
    crop = Image.fromarray(black[top:bottom, left:right].astype('uint8') * 255)
    # Preserve aspect ratio, center in a padded square to accommodate small
    # rasterization differences. Diamond position/scale is validated separately.
    scale = 64 / max(crop.size)
    crop = crop.resize((max(1, round(crop.width*scale)), max(1, round(crop.height*scale))), Image.Resampling.NEAREST)
    result = np.zeros((72, 72), dtype=bool)
    x, y = (72-crop.width)//2, (72-crop.height)//2
    result[y:y+crop.height, x:x+crop.width] = np.asarray(crop) > 0
    return result


@lru_cache(maxsize=16)
def _templates(size: int = 100) -> dict[str, np.ndarray]:
    result = {}
    for n in range(1, 10):
        code = f'GHS{n:02}'
        with fitz.open(stream=(ASSETS / f'{code}.svg').read_bytes(), filetype='svg') as svg:
            with fitz.open('pdf', svg.convert_to_pdf()) as pdf:
                factor = size / pdf[0].rect.width
                pix = pdf[0].get_pixmap(matrix=fitz.Matrix(factor, factor), alpha=False)
                rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                red = (rgb[:, :, 0] > 140) & (rgb[:, :, 1] < 125) & (rgb[:, :, 2] < 125)
                yy, xx = np.nonzero(red)
                shape = _black_shape(rgb[yy.min():yy.max()+1, xx.min():xx.max()+1])
                if shape is not None:
                    result[code] = shape
    return result


def _score(left: np.ndarray, right: np.ndarray) -> float:
    # Symmetric one-pixel-tolerant overlap. Penalize different ink coverage so a
    # filled diamond cannot match the interior of a detailed hazard silhouette.
    a = float((left & ndimage.binary_dilation(right)).sum()) / max(1, left.sum())
    b = float((right & ndimage.binary_dilation(left)).sum()) / max(1, right.sum())
    density = min(left.sum(), right.sum()) / max(1, max(left.sum(), right.sum()))
    return min(a, b) * (0.8 + 0.2 * density)


def _match_region(rgb: np.ndarray) -> list[str]:
    red = (rgb[:, :, 0] > 140) & (rgb[:, :, 1] < 125) & (rgb[:, :, 2] < 125)
    components, _ = ndimage.label(red)
    found = []
    for index, region in enumerate(ndimage.find_objects(components), 1):
        if region is None:
            continue
        sy, sx = region
        h, w = sy.stop-sy.start, sx.stop-sx.start
        if min(h, w) < 24 or max(h, w) > 600 or not 0.82 < w/h < 1.22:
            continue
        part = components[region] == index
        # Diamond border: red concentrated on four diagonal edges. Reject
        # rectangular logos and unrelated red artwork before matching glyphs.
        yy, xx = np.nonzero(part)
        diamond_distance = abs((xx-w/2)/(w/2)) + abs((yy-h/2)/(h/2))
        if np.mean((diamond_distance > 0.72) & (diamond_distance < 1.12)) < 0.88:
            continue
        candidate = _black_shape(rgb[region])
        if candidate is None:
            continue
        scores = {}
        nominal = round(max(h, w) * 1.02)
        for size in range(nominal-2, nominal+4):
            for code, template in _templates(size).items():
                scores[code] = max(scores.get(code, 0), _score(candidate, template))
        ranking = sorted(((score, code) for code, score in scores.items()), reverse=True)
        if len(ranking) > 1 and ranking[0][0] >= MIN_SCORE and ranking[0][0]-ranking[1][0] >= MIN_MARGIN:
            found.append(ranking[0][1])
    return found


def detect_pdf_pictograms(content: bytes) -> list[str]:
    """Return only high-confidence standard GHSxx icons located in SDS §2.2.

    At most the first eight pages are searched for the section and at most three
    pages rendered at 216dpi. No network requests or PDF scripts are executed.
    Unsupported layouts and extraction failures return an empty list.
    """
    if not content.lstrip().startswith(b'%PDF-'):
        return []
    try:
        with fitz.open(stream=content, filetype='pdf') as doc:
            regions = []
            in_labeling = False
            for page_number in range(min(len(doc), 8)):
                page = doc[page_number]
                text = page.get_text()
                starts = page.search_for('2.2')
                # A heading must identify labeling to avoid a table of contents
                # or an unrelated numeric occurrence in the body.
                has_heading = re.search(r'2\.2\.?\s*(?:Elementy|Oznakowanie|Label|Elements)', text, re.I)
                if not in_labeling and not has_heading:
                    continue
                top = starts[0].y0 if has_heading and starts else 0
                in_labeling = True
                ends = page.search_for('2.3')
                end = min((r.y0 for r in ends if r.y0 > top), default=page.rect.height)
                if end == page.rect.height:
                    ends = page.search_for('SEKCJA 3') + page.search_for('SECTION 3')
                    end = min((r.y0 for r in ends if r.y0 > top), default=page.rect.height)
                if end > top:
                    regions.append((page.number, fitz.Rect(0, top, page.rect.width, end)))
                if end < page.rect.height or len(regions) >= 3:
                    break
            found = []
            for page_no, clip in regions:
                # Malformed PDFs can advertise enormous physical page sizes.
                # Keep each raster bounded to 12 megapixels and 3x scale.
                scale = min(3.0, (12_000_000 / max(1, clip.width * clip.height)) ** 0.5)
                pix = doc[page_no].get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False, colorspace=fitz.csRGB)
                rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                found.extend(_match_region(rgb))
            return sorted(set(found))
    except (ValueError, RuntimeError, OSError, fitz.FileDataError):
        return []
