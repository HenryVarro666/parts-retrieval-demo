"""Upright RGB loading that survives a malformed EXIF block."""
import struct
from pathlib import Path

from PIL import Image

_ORIENTATION = 0x0112
# EXIF orientation -> the transpose that makes the image upright (what ImageOps.exif_transpose
# applies, without re-serialising the rest of the EXIF block, which can fail on bad tags).
_UPRIGHT = {
    2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180, 4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE, 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def orientation(im: Image.Image) -> int:
    """EXIF orientation 1-8; 1 when there is none, -1 when it cannot be read as a number in 1-8."""
    try:
        value = im.getexif().get(_ORIENTATION, 1)
    except (SyntaxError, struct.error, ValueError):
        return -1
    return value if isinstance(value, int) and 1 <= value <= 8 else -1


def upright_rgb(im: Image.Image) -> Image.Image:
    """Apply the EXIF rotation when one can be read, and convert to RGB."""
    turn = _UPRIGHT.get(orientation(im))
    if turn is not None:
        im = im.transpose(turn)
    return im.convert("RGB")


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return upright_rgb(im)
