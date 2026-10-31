"""Reproduce target-only crops from the three existing 80286 source photos."""
import csv
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps

root = Path(__file__).resolve().parent.parent
data = root / "data"
manifest = {r["file"]: r for r in csv.DictReader((data / "manifest.csv").open())}
directory = data / "multi_image/unit-01"
directory.mkdir(parents=True, exist_ok=True)
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
photos = []
for i, (page, crop) in enumerate([
    ("158840809", [20, 125, 146, 275]),
    ("158840810", [24, 128, 193, 326]),
    ("158840814", [15, 170, 245, 408]),
]):
    relative = f"images/raw/I80286/{page}.jpg"
    source = data / relative
    target = directory / f"photo-{i+1}.png"
    with Image.open(source) as image:
        ImageOps.exif_transpose(image).convert("RGB").crop(crop).save(target)
    row = manifest[relative]
    photos.append({"file": str(target.relative_to(data)), "sha256": digest(target),
                   "source": {"file": relative, "sha256": digest(source), "crop": crop,
                              "page_url": row["page_url"], "artist": row["artist"], "license": row["license"],
                              "change": "Target-only crop; no synthetic angle, rescaling or pixel edits"}})
doc = {"schema": 1, "scope": "exploratory_same_object", "groups": [{
    "object_id": "unit-01", "part_id": "I80286", "photos": photos,
    "identity_basis": {"status": "visually_supported", "reviewer": "Codex assistant, not a component expert",
        "evidence": "Same N80286-10 / SX004 markings, lower lot line, corner mould marks and visible wear in all three photos; Sgroey source series dated 2025-01-31 at 14:33:46, 14:31:06 and 14:29:00. Same physical unit is inferred from visible/source consistency, not confirmed by the owner.",
        "limitations": "One physical-unit hypothesis; mainly scale/framing changes and limited viewpoint variation. Low-resolution target crops from multi-chip comparison photos, not a dedicated close-up capture set. No population-level accuracy claim."}}]}
(data / "multi_image/manifest.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
print("Prepared 1 exploratory three-photo group; original source pixels unchanged.")
