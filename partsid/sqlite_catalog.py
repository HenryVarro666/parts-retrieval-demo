"""SQLite OCR keyword retrieval. Scores are evidence ranks, not probabilities."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from . import identifier

SCHEMA_VERSION = 1
_OWNER = "partsid.sqlite_catalog"
_WORD = re.compile(r"[A-Za-z0-9µμΜ]+")
_NOISE = {"LOT", "BATCH", "DATE", "CODE", "COPYRIGHT", "AND", "OR", "NOT", "NEAR"}
_BASE = {"exact": 1000, "folded": 900, "fuzzy": 100, "maker": 20, "fts": 10}


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _metadata(conn: sqlite3.Connection) -> dict:
    try:
        metadata = {row[0]: json.loads(row[1]) for row in conn.execute("SELECT key, value FROM metadata")}
        if metadata.get("owner") != _OWNER or metadata.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported catalog schema; explicitly rebuild the catalog")
        return metadata
    except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        raise ValueError("file is not a partsid SQLite catalog") from exc


def build_catalog(parts: list[dict], db_path: Path, references: list[dict] | None = None) -> dict:
    """Build atomically from public catalog data; replace only our own database."""
    db_path = Path(db_path)
    if db_path.exists():
        with closing(_connect(db_path)) as conn:
            _metadata(conn)
    refs = sorted({(r["part_id"], r["file"]) for r in references or []})
    ids = {p["id"] for p in parts}
    if len(ids) != len(parts) or any(pid not in ids for pid, _ in refs):
        raise ValueError("catalog IDs must be unique and references must belong to the catalog")
    metadata = {"owner": _OWNER, "schema_version": SCHEMA_VERSION,
                "sqlite_version": sqlite3.sqlite_version, "catalog_sha256": _sha(parts),
                "references_sha256": _sha(refs), "part_count": len(parts),
                "reference_count": len(refs), "confidence_calibrated": False,
                "keyword_policy": "deduplicated words and known 2/3-word joins within one OCR view; max 64 characters per word",
                "score_policy": "exact > folded > fuzzy > maker > FTS; bounded multi-keyword support"}
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=db_path.parent, prefix=f".{db_path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with closing(sqlite3.connect(temporary)) as conn, conn:
            conn.executescript("""
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE parts (part_id TEXT PRIMARY KEY, name TEXT, family TEXT, description TEXT);
                CREATE TABLE aliases (part_id TEXT, alias TEXT, normalized TEXT, folded TEXT,
                                      PRIMARY KEY (part_id, alias));
                CREATE INDEX alias_normalized ON aliases(normalized);
                CREATE INDEX alias_folded ON aliases(folded);
                CREATE TABLE makers (part_id TEXT, maker TEXT, normalized TEXT, folded TEXT,
                                     PRIMARY KEY (part_id, maker));
                CREATE INDEX maker_normalized ON makers(normalized);
                CREATE INDEX maker_folded ON makers(folded);
                CREATE TABLE alias_grams (gram TEXT, part_id TEXT, alias TEXT,
                                          PRIMARY KEY (gram, part_id, alias));
                CREATE TABLE reference_images (part_id TEXT, file TEXT, PRIMARY KEY (part_id, file));
                CREATE VIRTUAL TABLE part_fts USING fts5(part_id UNINDEXED, name, family, description);
            """)
            conn.executemany("INSERT INTO metadata VALUES (?, ?)", [(k, _canonical(v)) for k, v in sorted(metadata.items())])
            conn.executemany("INSERT INTO reference_images VALUES (?, ?)", refs)
            for part in sorted(parts, key=lambda p: p["id"]):
                row = (part["id"], part.get("name", ""), part.get("family", ""), part.get("description", ""))
                conn.execute("INSERT INTO parts VALUES (?, ?, ?, ?)", row)
                conn.execute("INSERT INTO part_fts VALUES (?, ?, ?, ?)", row)
                for field, table, values in [("alias", "aliases", part.get("aliases", [])),
                                              ("maker", "makers", part.get("makers", []))]:
                    for value in sorted(set(values)):
                        normalized = identifier.normalize(value)
                        if not normalized:
                            continue
                        conn.execute(f"INSERT INTO {table} VALUES (?, ?, ?, ?)",
                                     (part["id"], value, normalized, normalized.translate(identifier._FOLD)))
                        if field == "alias":
                            conn.executemany("INSERT INTO alias_grams VALUES (?, ?, ?)",
                                             [(g, part["id"], value) for g in sorted(identifier.trigrams(normalized))])
        temporary.replace(db_path)
    finally:
        temporary.unlink(missing_ok=True)
    return metadata


def _lookup(conn: sqlite3.Connection, table: str, normalized: str, *, contained=False) -> list[sqlite3.Row]:
    # Table is selected internally, never from OCR. Both branches use real indexes.
    values = {normalized}
    if contained and not normalized.isdigit():
        values.update(normalized[i:j] for i in range(len(normalized)) for j in range(i + 4, len(normalized) + 1))
    folded = sorted({v.translate(identifier._FOLD) for v in values})
    values = sorted(values)
    query = (f"SELECT * FROM {table} WHERE normalized IN ({','.join('?' for _ in values)}) "
             f"OR folded IN ({','.join('?' for _ in folded)}) ORDER BY part_id, 2")
    return conn.execute(query, values + folded).fetchall()


def _model_like(normalized: str) -> bool:
    if len(normalized) < 4 or not any(c.isdigit() for c in normalized) or not any(c.isalpha() for c in normalized):
        return False
    # Typical YYWW/lot text, including one misread digit, is not a fuzzy model read.
    return not re.fullmatch(r"[0-9]{3,}[A-Z]{0,3}", normalized)


def _aliases(conn: sqlite3.Connection, text: str, normalized: str) -> list[dict]:
    rows = _lookup(conn, "aliases", normalized, contained=True)
    hits = []
    for row in rows:
        score, _ = identifier.score_part(text, [row["alias"]])
        if score >= identifier.FOLDED:
            hits.append({**dict(row), "strength": score, "kind": "exact" if score == 1 else "folded"})
    if hits or not _model_like(normalized):
        return hits
    grams = sorted(identifier.trigrams(normalized))
    rows = conn.execute(f"""SELECT DISTINCT a.* FROM aliases a JOIN alias_grams g
                             ON a.part_id = g.part_id AND a.alias = g.alias
                             WHERE g.gram IN ({','.join('?' for _ in grams)})
                             ORDER BY a.part_id, a.alias""", grams)
    for row in rows:
        score, _ = identifier.score_part(text, [row["alias"]])
        if identifier.MIN_SCORE <= score < identifier.FOLDED:
            hits.append({**dict(row), "strength": score, "kind": "fuzzy"})
    return hits


def _sources(text: str, boxes: list[dict] | None) -> list[str]:
    views = defaultdict(list)
    for box in boxes or []:
        if box.get("text"):
            views[str(box.get("view_id", box.get("view", "selected")))].append(str(box["text"]))
    return [" ".join(words) for words in views.values()] if views else [text]


def _terms(conn: sqlite3.Connection, text: str, boxes: list[dict] | None) -> list[tuple[str, str]]:
    terms = {}
    for source in _sources(text, boxes):
        for line in source.splitlines():
            words = [m for m in _WORD.finditer(line) if len(m.group()) <= 64]
            for word in words:
                terms.setdefault(identifier.normalize(word.group()), word.group())
            for size in (2, 3):
                for i in range(len(words) - size + 1):
                    joined = line[words[i].start():words[i + size - 1].end()]
                    normalized = identifier.normalize(joined)
                    if len(normalized) <= 64 and (_lookup(conn, "aliases", normalized) or _lookup(conn, "makers", normalized)):
                        terms.setdefault(normalized, joined)
    return [(text, normalized) for normalized, text in terms.items()]


class SQLiteCatalog:
    """Reusable across HTTP threads: no connection is retained on this object."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise FileNotFoundError(self.db_path)
        with closing(_connect(self.db_path)) as conn:
            self.metadata = _metadata(conn)

    def search(self, ocr_text: str, limit: int = 10, boxes: list[dict] | None = None) -> dict:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        keywords, matches = [], defaultdict(list)
        with closing(_connect(self.db_path)) as conn:
            for text, normalized in _terms(conn, ocr_text, boxes):
                aliases = _aliases(conn, text, normalized)
                makers = _lookup(conn, "makers", normalized)
                kind = ("model" if aliases or _model_like(normalized) else "maker" if makers else
                        "description" if normalized.isalpha() and len(normalized) >= 3 and normalized not in _NOISE else "noise")
                keywords.append({"text": text, "normalized": normalized, "kind": kind})
                best_aliases = {}
                for alias in aliases:
                    pid = alias["part_id"]
                    previous = best_aliases.get(pid)
                    if previous is None or (alias["strength"], len(alias["normalized"])) > (previous["strength"], len(previous["normalized"])):
                        best_aliases[pid] = alias
                for pid, alias in best_aliases.items():
                    matches[pid].append({"term": text, "field": "aliases", "kind": alias["kind"],
                                         "matched_alias": alias["alias"], "matched_value": alias["alias"], "strength": alias["strength"]})
                for maker in makers:
                    matches[maker["part_id"]].append({"term": text, "field": "makers", "kind": "maker",
                                                      "matched_alias": None, "matched_value": maker["maker"], "strength": 0.3})
                if kind == "description":
                    # Only one sanitized, quoted token is sent to FTS; operators stay text.
                    expression = '"' + normalized.replace('"', '""') + '"'
                    for row in conn.execute("SELECT * FROM part_fts WHERE part_fts MATCH ?", (expression,)):
                        for field in ("name", "family", "description"):
                            if normalized in {identifier.normalize(w) for w in _WORD.findall(row[field])}:
                                matches[row["part_id"]].append({"term": text, "field": field, "kind": "fts",
                                                                "matched_alias": None, "matched_value": normalized, "strength": 0.1})
        candidates = []
        for pid, receipts in matches.items():
            tier = max((m["kind"] for m in receipts), key=_BASE.get)
            support = {}
            for receipt in receipts:
                key = identifier.normalize(receipt["term"])
                support[key] = max(support.get(key, 0.0), receipt["strength"])
            total = sum(support.values())
            candidates.append({"part_id": pid, "score": _BASE[tier] + total / (1 + total), "tier": tier, "matches": receipts})
        candidates.sort(key=lambda p: (-p["score"], p["part_id"]))
        return {"keywords": keywords, "candidates": candidates[:limit],
                "strong_ids": [p["part_id"] for p in candidates if p["tier"] in {"exact", "folded"}],
                "metadata": dict(self.metadata)}
