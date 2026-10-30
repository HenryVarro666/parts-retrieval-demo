"""Tile each part's downloaded photos into one labelled sheet for manual curation.

    python -I -m partsid.contact_sheet   ->  results/contact_sheets/<part_id>.jpg
"""
import csv
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

from .images import load_rgb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "results" / "contact_sheets"
TILE, COLS = 320, 4


def main() -> None:
    by_part = defaultdict(list)
    with open(DATA / "manifest.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_part[row["part_id"]].append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    for part_id, rows in by_part.items():
        n_rows = (len(rows) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * TILE, n_rows * (TILE + 24)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(rows):
            im = load_rgb(DATA / row["file"])  # upright, as the pipeline sees it
            im.thumbnail((TILE, TILE))
            x, y = (i % COLS) * TILE, (i // COLS) * (TILE + 24)
            sheet.paste(im, (x + (TILE - im.width) // 2, y + 24))
            draw.text((x + 4, y + 4), f"[{i}] {row['pageid']}", fill="black")
        sheet.save(OUT / f"{part_id}.jpg", quality=85)
    print(f"{len(by_part)} sheets -> {OUT}")


if __name__ == "__main__":
    main()
