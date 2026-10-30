"""In-memory catalog index: one text document per part, one or more reference images per part.

Brute-force cosine over numpy rows. At catalog scale this is the job of pgvector
(`ORDER BY embedding <=> $1`); with 18 parts a matrix product is enough.
"""
import numpy as np


def part_document(part: dict) -> str:
    return (f"{part['name']}. Part numbers: {', '.join(part['aliases'])}. "
            f"Makers: {', '.join(part['makers'])}. {part['description']}")


class CatalogIndex:
    def __init__(self, parts: list[dict], text_vecs: np.ndarray, image_vecs: np.ndarray, image_part_ids: list[str]):
        self.parts = parts
        self.part_ids = [p["id"] for p in parts]
        self.text_vecs = text_vecs
        self.image_vecs = image_vecs
        self.image_part_ids = image_part_ids

    def search_text(self, qvec: np.ndarray) -> list[tuple[str, float]]:
        sims = self.text_vecs @ qvec
        return [(self.part_ids[i], float(sims[i])) for i in np.argsort(-sims)]

    def search_image(self, qvec: np.ndarray) -> list[tuple[str, float]]:
        """Score each part by its closest reference image."""
        sims = self.image_vecs @ qvec
        best: dict[str, float] = {}
        for pid, s in zip(self.image_part_ids, sims):
            best[pid] = max(best.get(pid, -1.0), float(s))
        return sorted(best.items(), key=lambda kv: -kv[1])
