"""Rebuild the frozen public triplet crops offline; never downloads or runs models."""
import copy
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps


def prepare(root):
    data = Path(root) / "data"
    selection = data / "public_triplets/selection.json"
    doc = json.loads(selection.read_text())
    if doc.get("inference_run_at_freeze") is not False:
        raise ValueError("Expected a selection frozen before inference")
    output = copy.deepcopy(doc)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for group in output["groups"]:
        for i, photo in enumerate(group["photos"], 1):
            source = photo["source"]
            path = (data / source["file"]).resolve()
            if not path.is_relative_to(data.resolve()) or digest(path) != source["sha256"]:
                raise ValueError("Frozen source bytes changed")
            box = source["crop"]
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                if (len(box) != 4 or not all(type(v) is int for v in box)
                        or not (0 <= box[0] < box[2] <= im.width and 0 <= box[1] < box[3] <= im.height)):
                    raise ValueError("Invalid frozen crop")
                target = data / "public_triplets" / group["object_id"] / f"photo-{i}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                im.crop(box).save(target)
            photo.update(file=str(target.relative_to(data)), sha256=digest(target))
    output["selection_file"] = str(selection.relative_to(Path(root)))
    output["selection_sha256"] = digest(selection)
    path = data / "public_triplets/manifest.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    return path


if __name__ == "__main__":
    print(prepare(Path(__file__).resolve().parent.parent))
