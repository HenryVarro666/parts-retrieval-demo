"""Conservative foreground geometry, independent of OCR and catalog identities.

Fixed v1 rules (chosen before evaluation): process at most 384px per side;
estimate a median CIELAB border background; require border p95 distance <=25;
threshold foreground at max(25, Otsu distance). Reject <16px/<0.2% or >80%
foreground, <85% largest-component share, and any component edge contact.
Descriptors describe a silhouette only, never packages, pins or physical size.
"""
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

METHOD = "border_lab_otsu_v1"
MAX_SIDE = 384


def _unknown(note: str) -> dict:
    return {"available": False, "method": METHOD, "bbox": None,
            "features": {}, "quality_notes": [note]}


def describe_shape(path: Path) -> dict:
    """Return JSON geometry in upright original-pixel coordinates, or unknown.

    The bounding box is half-open: [x0, y0, x1, y1]. Border consistency and
    component checks are conservative heuristics, not a guarantee of detection.
    Transparent pixels are composited on white before segmentation.
    """
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
            image = image.convert("RGB")
            original_width, original_height = image.size
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.BILINEAR)
            pixels = np.asarray(image)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return _unknown("Image could not be read or oriented.")

    height, width = pixels.shape[:2]
    if min(width, height) < 3:
        return _unknown("Image is too small for foreground geometry.")
    lab = cv2.cvtColor(pixels, cv2.COLOR_RGB2LAB).astype(np.float32)
    # Each outer-edge pixel is sampled once; thick strips can include the part.
    border = np.concatenate((lab[0], lab[-1], lab[1:-1, 0], lab[1:-1, -1]))
    background = np.median(border, axis=0)
    border_distance = np.linalg.norm(border - background, axis=1)
    if float(np.percentile(border_distance, 95)) > 25.0:
        return _unknown("Nonuniform border background makes segmentation unreliable.")

    distance = np.linalg.norm(lab - background, axis=2)
    distance_u8 = np.minimum(np.rint(distance), 255).astype(np.uint8)
    otsu, _ = cv2.threshold(distance_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = (distance > max(25.0, float(otsu))).astype(np.uint8)
    foreground = int(mask.sum())
    if foreground < max(16, width * height * 0.002):
        return _unknown("No sufficiently large foreground was separated from the background.")
    if foreground > width * height * 0.8:
        return _unknown("Foreground occupies too much of the image for reliable segmentation.")

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    component_id = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    component_area = int(stats[component_id, cv2.CC_STAT_AREA])
    if count < 2 or component_area / foreground < 0.85:
        return _unknown("Fragmented foreground has no sufficiently dominant component.")
    component = (labels == component_id).astype(np.uint8)
    if (component[0].any() or component[-1].any()
            or component[:, 0].any() or component[:, -1].any()):
        return _unknown("Foreground touches the image edge and may be clipped.")

    contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
    side_a, side_b = cv2.minAreaRect(contour)[1]
    if min(side_a, side_b, area, perimeter, hull_area) <= 0:
        return _unknown("Foreground contour is degenerate.")

    x, y, box_width, box_height = cv2.boundingRect(contour)
    scale_x, scale_y = original_width / width, original_height / height
    bbox = [math.floor(x * scale_x), math.floor(y * scale_y),
            min(original_width, math.ceil((x + box_width) * scale_x)),
            min(original_height, math.ceil((y + box_height) * scale_y))]
    features = {
        "elongation": float(max(side_a, side_b) / min(side_a, side_b)),
        "solidity": float(min(1.0, area / hull_area)),
        "circularity": float(min(1.0, 4 * math.pi * area / (perimeter * perimeter))),
    }
    return {"available": True, "method": METHOD, "bbox": bbox,
            "features": features,
            "quality_notes": ["Heuristic silhouette; package type, pins and physical size remain unknown."]}


def compare_shapes(query: dict, reference: dict) -> float | None:
    """Symmetric uncalibrated similarity in [0,1]; unknown evidence abstains.

    Equal contributions use fixed distance scales: 2x elongation, 0.2 solidity,
    and 0.2 circularity. Neither orientation nor raw pixel size is compared.
    A single reference may not represent package variants; use only soft ranks.
    """
    values = []
    for description in (query, reference):
        if not description.get("available"):
            return None
        try:
            feature = description["features"]
            elongation, solidity, circularity = (float(feature[name]) for name in
                                               ("elongation", "solidity", "circularity"))
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if (not all(math.isfinite(x) for x in (elongation, solidity, circularity))
                or elongation < 1 or not 0 < solidity <= 1 or not 0 < circularity <= 1):
            return None
        values.append((math.log(elongation), solidity, circularity))
    distance = sum(abs(a - b) / scale for a, b, scale in
                   zip(values[0], values[1], (math.log(2), 0.2, 0.2))) / 3
    return float(math.exp(-distance))
