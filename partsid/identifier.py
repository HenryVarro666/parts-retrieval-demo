"""Identifier channel: match OCR text against catalog part numbers.

Similarity follows PostgreSQL pg_trgm: each word is lower-cased and padded with
two spaces in front and one behind, and similarity is |A & B| / |A | B| over the
two trigram sets. A whole alias found inside an OCR token counts as an exact hit,
but an alias shorter than 4 characters only when it is the whole token.
"""
import re

_WORD = re.compile(r"[A-Za-z0-9]+")

# Glyphs OCR often swaps on laser-etched markings. Both sides are folded the
# same way, and a folded-only match scores a little below an exact one.
_FOLD = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8"})
# Letters a misread digit can turn into; used only to tell a date code from a part number.
_LOOKALIKE = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "G": "6", "B": "8"})
EXACT, FOLDED = 1.0, 0.9
MIN_SCORE = 0.35  # below this the channel abstains for that part
LONG_ALIAS = 6  # aliases this long may also match across three OCR words ("ESP-WROOM-32")


def _micro_to_u(text: str) -> str:
    # "µA741" is spelled "UA741" in ASCII. Replace before upper(): "µ".upper() is Greek capital Mu.
    return re.sub("[µμΜ]", "U", text)


def normalize(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _micro_to_u(text).upper())


def trigrams(text: str) -> set[str]:
    grams = set()
    for word in _WORD.findall(text.lower()):
        padded = f"  {word} "
        grams.update(padded[i:i + 3] for i in range(len(padded) - 2))
    return grams


def similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def ocr_tokens(ocr_text: str) -> tuple[list[str], list[str]]:
    """Words plus adjacent-word joins, since OCR splits "ESP-12F" or "ATMEGA328P -PU";
    and, separately, three-word joins for long aliases such as "ESP-WROOM-32"."""
    words = [w.upper() for w in _WORD.findall(_micro_to_u(ocr_text))]
    pairs = [a + b for a, b in zip(words, words[1:])]
    triples = [a + b + c for a, b, c in zip(words, words[1:], words[2:])]
    return words + pairs, triples


def _contains(alias: str, token: str) -> bool:
    # Short aliases such as "555" or "741" must match a whole token, otherwise
    # they fire on date codes and lot numbers.
    return alias == token or (len(alias) >= 4 and alias in token)


def _folded_hit(a_fold: str, token: str) -> bool:
    """A fold may repair a misread part number, not build one out of letters alone."""
    t_fold = token.translate(_FOLD)
    if not _contains(a_fold, t_fold):
        return False
    if any(c.isalpha() for c in a_fold):
        return True  # a letter the fold leaves alone (Z, E, M, N, P) still matched literally
    i = t_fold.find(a_fold)
    while i != -1:  # an all-digit alias needs a real digit inside the matched span: "SSS" is not "555"
        if any(c.isdigit() for c in token[i:i + len(a_fold)]):
            return True
        i = t_fold.find(a_fold, i + 1)
    return False


def _trigram_ok(alias: str, token: str) -> bool:
    # Trigram overlap says little about short strings ("55" vs "555" is 0.75), and
    # all-digit tokens are date codes, years and row numbers more often than reads.
    # That holds for a date code with one misread glyph too ("741O" is week 10 of 1974),
    # so letters must survive mapping lookalikes back to digits, unless the token starts
    # with one: part numbers open with a maker prefix ("L317"), date codes with a digit.
    if len(alias) < 4 or len(token) < 4 or not any(c.isdigit() for c in token):
        return False
    return token[0].isalpha() or any(c.isalpha() for c in token.translate(_LOOKALIKE))


def score_part(ocr_text: str, aliases: list[str]) -> tuple[float, str]:
    """Best (score, alias) over every alias and OCR token; equal scores keep the longer alias."""
    tokens, triples = ocr_tokens(ocr_text)
    best, best_len = (0.0, ""), 0
    for alias in aliases:
        a = normalize(alias)
        a_fold = a.translate(_FOLD)
        scores = []
        for t in tokens:
            if _contains(a, t):
                scores.append(EXACT)
            elif _folded_hit(a_fold, t):
                scores.append(FOLDED)
            elif _trigram_ok(a, t):
                scores.append(similarity(a, t))
        if len(a) >= LONG_ALIAS:
            scores += [EXACT if a in t else FOLDED for t in triples if a in t or _folded_hit(a_fold, t)]
        s = max(scores, default=0.0)
        if s > 0 and (s, len(a)) > (best[0], best_len):
            best, best_len = (s, alias), len(a)
    return best


def rank(ocr_text: str, parts: list[dict], min_score: float = MIN_SCORE) -> list[tuple[str, float, str]]:
    """Parts whose best alias clears min_score, as (part_id, score, matched_alias), best first.

    Equal scores go to the part whose matched alias is longer, so "D8086" beats a
    "7805" date code; remaining ties keep catalog order.
    """
    scored = [(p["id"], *score_part(ocr_text, p["aliases"])) for p in parts]
    return sorted((s for s in scored if s[1] >= min_score), key=lambda s: (-s[1], -len(normalize(s[2]))))


def for_fusion(hits: list[tuple[str, float, str]]) -> list[str]:
    """The identifier ranking handed to fusion: only the strong hits when there are any.

    An exact or folded read of a part number should not be diluted by the weak
    trigram neighbours that rank right behind it (8088 -> 8086, 8085, 8080).
    """
    strong = [pid for pid, s, _ in hits if s >= FOLDED]
    return strong or [pid for pid, _, _ in hits]
