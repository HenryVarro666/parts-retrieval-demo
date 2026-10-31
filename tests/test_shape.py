"""Pixel-only shape evidence on hand-drawn geometry, without catalog labels."""
import json
import math

import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def rectangle():
    image = Image.new("RGB", (240, 180), "white")
    ImageDraw.Draw(image).rectangle((60, 60, 179, 99), fill="black")
    return image


def save(image, tmp_path, name="photo.png"):
    path = tmp_path / name
    image.save(path)
    return path


def test_rectangle_has_pixel_bbox_and_finite_shape_features(tmp_path, rectangle):
    # Catches missing foreground extraction and accidentally serializing NumPy values.
    from partsid.shape import describe_shape

    result = describe_shape(save(rectangle, tmp_path))
    assert result["available"] is True
    assert result["bbox"] == [60, 60, 180, 100]
    assert result["method"]
    assert result["features"]["elongation"] == pytest.approx(3.0, abs=0.1)
    assert result["features"]["solidity"] == pytest.approx(1.0, abs=0.01)
    assert all(isinstance(x, float) and math.isfinite(x) for x in result["features"].values())
    json.dumps(result, allow_nan=False)


def test_shape_similarity_survives_a_quarter_turn(tmp_path, rectangle):
    # Catches use of axis-aligned aspect ratio or orientation in comparison.
    from partsid.shape import compare_shapes, describe_shape

    original = describe_shape(save(rectangle, tmp_path))
    turned = describe_shape(save(rectangle.transpose(Image.Transpose.ROTATE_90), tmp_path, "turned.png"))
    assert turned["available"] is True
    assert compare_shapes(original, turned) == pytest.approx(1.0, abs=0.01)


def test_shape_similarity_survives_a_diagonal_turn(tmp_path, rectangle):
    # Catches axis-aligned measurements despite a passing 90-degree comparison.
    from partsid.shape import compare_shapes, describe_shape

    original = describe_shape(save(rectangle, tmp_path))
    turned = describe_shape(save(rectangle.rotate(35, expand=True, fillcolor="white"), tmp_path, "diagonal.png"))
    assert turned["available"] is True
    assert turned["features"]["elongation"] == pytest.approx(3.0, abs=0.15)
    assert compare_shapes(original, turned) > 0.75


def test_circle_is_more_similar_to_itself_than_an_elongated_rectangle(tmp_path, rectangle):
    # Catches constant scores and inverted feature-distance ordering.
    from partsid.shape import compare_shapes, describe_shape

    image = Image.new("RGB", (240, 180), "white")
    ImageDraw.Draw(image).ellipse((80, 50, 159, 129), fill="black")
    circle = describe_shape(save(image, tmp_path, "circle.png"))
    elongated = describe_shape(save(rectangle, tmp_path))
    assert circle["available"] is True
    assert circle["features"]["elongation"] == pytest.approx(1.0, abs=0.05)
    assert circle["features"]["circularity"] > elongated["features"]["circularity"]
    assert compare_shapes(circle, circle) == pytest.approx(1.0)
    assert compare_shapes(circle, elongated) < 0.8
    assert compare_shapes(circle, elongated) == compare_shapes(elongated, circle)


@pytest.mark.parametrize("kind", ["blank", "busy_border", "fragmented", "edge_touch", "huge", "tiny"])
def test_unreliable_foreground_has_no_shape_evidence(tmp_path, kind):
    # Catches accidental confidence on ambiguous backgrounds or unusable masks.
    from partsid.shape import describe_shape

    image = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(image)
    if kind == "busy_border":
        for y in range(0, 200, 10):
            for x in range(0, 200, 10):
                if (x + y) % 20 == 0:
                    draw.rectangle((x, y, x + 9, y + 9), fill="black")
    elif kind == "fragmented":
        draw.rectangle((30, 60, 69, 139), fill="black")
        draw.rectangle((130, 60, 169, 139), fill="black")
    elif kind == "edge_touch":
        draw.rectangle((0, 99, 100, 101), fill="black")
    elif kind == "huge":
        draw.rectangle((5, 5, 194, 194), fill="black")
    elif kind == "tiny":
        draw.rectangle((99, 99, 100, 100), fill="black")
    result = describe_shape(save(image, tmp_path))
    assert result["available"] is False
    assert result["features"] == {}
    assert result["bbox"] is None
    assert result["quality_notes"]
    json.dumps(result, allow_nan=False)


def test_missing_or_invalid_image_returns_unknown(tmp_path):
    # Catches leaking read errors into a retrieval request.
    from partsid.shape import describe_shape

    invalid = tmp_path / "invalid.png"
    invalid.write_text("not an image")
    for path in (tmp_path / "missing.png", invalid):
        result = describe_shape(path)
        assert result["available"] is False
        assert result["features"] == {}
        assert result["quality_notes"]


def test_unavailable_or_nonfinite_shape_comparison_abstains(tmp_path, rectangle):
    # Catches treating unknown evidence as zero or letting NaNs enter ranking.
    from partsid.shape import compare_shapes, describe_shape

    known = describe_shape(save(rectangle, tmp_path))
    for unknown in ({"available": False}, {"available": True, "features": {}},
                    {"available": True, "features": {"elongation": float("nan"), "solidity": 1.0, "circularity": 1.0}}):
        assert compare_shapes(known, unknown) is None
        assert compare_shapes(unknown, known) is None


def test_large_image_bbox_maps_to_upright_original_pixels(tmp_path, rectangle):
    # Catches returning bounded-processing coordinates for a larger source photo.
    from partsid.shape import describe_shape

    large = rectangle.resize((2400, 1800), Image.Resampling.NEAREST)
    result = describe_shape(save(large, tmp_path))
    assert result["available"] is True
    assert result["bbox"] == pytest.approx([600, 600, 1800, 1000], abs=12)


def test_exif_rotation_is_applied_before_returning_bbox(tmp_path):
    # Catches measuring the encoded raster instead of the displayed upright image.
    from partsid.shape import describe_shape

    image = Image.new("RGB", (120, 80), "white")
    ImageDraw.Draw(image).rectangle((20, 10, 79, 29), fill="black")
    exif = image.getexif()
    exif[274] = 6
    path = tmp_path / "oriented.png"
    image.save(path, exif=exif)
    result = describe_shape(path)
    assert result["available"] is True
    assert result["bbox"] == [50, 20, 70, 80]
