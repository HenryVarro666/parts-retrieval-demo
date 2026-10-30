"""OCR engines behind one interface: read(image_path) -> text.

EasyOCR (CRAFT detector + CRNN recogniser, PyTorch) is the main engine;
Tesseract is the classic baseline the eval compares it against. Both read the
file themselves, so the evaluation hands them upright copies of any photo that
carries an EXIF rotation (evaluate.upright_path).
"""
import warnings
from pathlib import Path

# EasyOCR's DataLoader asks for pinned memory on every call; MPS has none and says so each time.
warnings.filterwarnings("ignore", message=".*'pin_memory' argument is set as true but not supported on MPS.*")

MIN_CONF = 0.2  # EasyOCR boxes below this confidence are mostly noise on chip photos
TESS_MIN_CONF = 60  # Tesseract word confidence (0-100); the customary pytesseract cut-off


class EasyOCREngine:
    def __init__(self, device: str, rotations: bool = False):
        import easyocr

        self.name = "easyocr+rot" if rotations else "easyocr"
        # quantize=False: EasyOCR otherwise swaps in an int8 recogniser on CPU only,
        # which would make CPU results differ from MPS and CUDA ones.
        self.reader = easyocr.Reader(["en"], gpu=device, quantize=False, verbose=False)
        # Chips are often photographed sideways; trying 90/180/270 costs ~4x time.
        self.rotation_info = [90, 180, 270] if rotations else None

    def read(self, image_path: Path) -> str:
        results = self.reader.readtext(str(image_path), detail=1, rotation_info=self.rotation_info)
        return " ".join(text for _, text, conf in results if conf >= MIN_CONF)


class TesseractEngine:
    name = "tesseract"

    def read(self, image_path: Path) -> str:
        import pytesseract

        # psm 11: sparse text, no layout assumptions. A str path lets tesseract read
        # the stored file itself; a PIL image would go through a lossy JPEG re-save.
        d = pytesseract.image_to_data(str(image_path), config="--psm 11", output_type=pytesseract.Output.DICT)
        return " ".join(w.strip() for w, c in zip(d["text"], d["conf"]) if w.strip() and float(c) >= TESS_MIN_CONF)


def make_engine(name: str, device: str):
    if name == "easyocr":
        return EasyOCREngine(device)
    if name == "easyocr+rot":
        return EasyOCREngine(device, rotations=True)
    if name == "tesseract":
        return TesseractEngine()
    raise ValueError(f"unknown OCR engine: {name}")
