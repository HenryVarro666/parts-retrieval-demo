"""Download public photos of each catalog part from Wikimedia Commons.

Reads data/parts.json and, per part, takes in page-id order the first JPEG files
whose titles pass NOT_A_PART_PHOTO: up to --per-part from the part's own Commons
category, then up to --per-part-sub more from its part-number subcategories
(e.g. "Intel D8086"; listed by hand in parts.json, never computers, boards or
second sources). Saves images upright and at most 960px wide under
data/images/raw/<part_id>/ and records each file's Commons page with its license
and author in data/manifest.csv.

Categories change over time, so the manifest, not a new listing, defines the
dataset: --from-manifest downloads exactly the files it lists, each from the URL
recorded for it, and accepts only a file of the recorded size; anything else is
reported as not fetched. A row with no recorded URL is fetched from today's
choices (the 960px thumbnail, else the original shrunk locally). Only the size
is checked, not the content: the manifest records no checksums.

Requests are serial and paced. Commons API listing requests back off and retry
on HTTP 429, 5xx and network errors; image downloads (curl, see download()) are
tried once per URL and not retried within a run. A file that cannot be fetched
keeps its manifest row, and the run exits with status 1; a rerun retries only
those files.

    python -I -m partsid.fetch_commons --from-manifest       # fetch the manifest's files missing from data/images
    python -I -m partsid.fetch_commons --per-part 16 --per-part-sub 16   # list Commons again
"""
import argparse
import csv
import hashlib
import html
import http.client
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from .images import orientation, upright_rgb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://commons.wikimedia.org/w/api.php"
UA = "parts-retrieval-demo/0.1 (personal research demo; https://commons.wikimedia.org/wiki/Commons:API)"
MAX_WIDTH = 960  # a standard Commons thumbnail width; also the local storage width
HEADERS = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
FIELDS = ["part_id", "file", "pageid", "title", "page_url", "license", "artist", "width", "height",
          "file_url", "image_url", "stored_width", "stored_height"]


def candidate_urls(file_url: str, width: int) -> list[str]:
    """The 960px thumbnail when the original is wider, then the original itself."""
    if width <= MAX_WIDTH:
        return [file_url]
    head, name = file_url.rsplit("/", 1)
    head = head.replace("/wikipedia/commons/", "/wikipedia/commons/thumb/", 1)
    return [f"{head}/{name}/{MAX_WIDTH}px-{name}", file_url]


def download(urls: list[str], path: Path, *, pause: float,
             size: tuple[int, int] | None = None) -> tuple[str | None, str]:
    """Fetch the first URL that yields a complete image: (url, "") or (None, why not).

    upload.wikimedia.org throttles thumbnail *rendering*: an uncached thumbnail
    URL that drew a 429 keeps failing for a long while. Originals are stored
    files served from cache, so on any failure fall back to the original and
    shrink it locally. curl is used because Python urllib drew 429s in moments
    when curl got 200 for the same URL. curl writes to a side file that replaces
    `path` only once the image decodes (and, given `size`, has that size), so an
    interrupted run never leaves a truncated file that a rerun would take as done,
    and a rebuild never takes a file of another size.
    """
    tmp = path.with_name(path.name + ".part")
    reason = ""
    for url in urls:
        proc = subprocess.run(
            ["curl", "-sS", "-L", "--connect-timeout", "20", "--max-time", "300",
             "-A", UA, "-o", str(tmp), "-w", "%{http_code}", url],
            capture_output=True, text=True, check=False,
        )
        time.sleep(pause)
        code = proc.stdout.strip()
        if proc.returncode == 0 and code == "200":
            try:
                got = _normalize(tmp)
            except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:  # truncated, or not an image
                reason = f"bad image: {e}"
            else:
                if size is None or got == size:
                    tmp.replace(path)
                    return url, ""
                reason = f"got {got[0]}x{got[1]}, the manifest records {size[0]}x{size[1]}"
        else:
            reason = f"HTTP {code}" if proc.returncode == 0 else f"curl exit {proc.returncode}"
        tmp.unlink(missing_ok=True)
    return None, reason


def _normalize(path: Path) -> tuple[int, int]:
    """Decode fully; apply any EXIF rotation and shrink to MAX_WIDTH, rewriting only when needed.

    Returns the stored size. A file with an EXIF block that cannot be parsed is
    rewritten without it, so every reader downstream sees the same pixels.
    """
    with Image.open(path) as im:
        im.load()
        if im.width <= MAX_WIDTH and orientation(im) == 1:
            return im.size
        im = upright_rgb(im)
    im.thumbnail((MAX_WIDTH, MAX_WIDTH * 4))
    im.save(path, format="JPEG", quality=90)
    return im.size


def _get(url: str, *, pause: float) -> bytes:
    backoff = 20
    for _ in range(5):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            time.sleep(pause)
            return body
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            # Retrying right at Retry-After kept hitting the same window; back off harder.
            retry_after = e.headers.get("Retry-After") or "0"
            wait = max(int(retry_after) if retry_after.isdigit() else 0, backoff)
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException):
            wait = backoff  # network trouble (refused, reset, cut short), not an answer
        time.sleep(wait)
        backoff *= 2
    raise RuntimeError(f"still failing after retries: {url}")


# Titles that mark drawings, die shots and the like rather than photos of the
# packaged part. Pure metadata filter, applied before any manual curation.
NOT_A_PART_PHOTO = re.compile(
    r"\b(die|decap\w*|schematic\w*|diagram\w*|pinout|pin-out|layout|mask|wafer|logo|"
    r"motherboard|mainboard|breadboard|waveform|symbol|datasheet|x-ray|micrograph\w*|block)\b",
    re.IGNORECASE,
)


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def _category_pages(category: str) -> list[dict]:
    q = {
        "action": "query", "format": "json", "maxlag": "5",
        "generator": "categorymembers", "gcmtitle": f"Category:{category}",
        "gcmtype": "file", "gcmlimit": "100",
        "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist",
    }
    pages, cont, lagged = [], {}, 0
    while True:
        data = json.loads(_get(f"{API}?{urllib.parse.urlencode({**q, **cont})}", pause=2.0))
        err = data.get("error")
        if err:
            # The API reports errors, maxlag included, with HTTP 200: never read one as an empty category.
            if err.get("code") != "maxlag" or lagged == 5:
                raise RuntimeError(f"Commons API error for {category}: {err.get('code')}: {err.get('info')}")
            lagged += 1
            time.sleep(10 * lagged)
            continue
        pages += data.get("query", {}).get("pages", {}).values()
        if "continue" not in data:
            return pages
        cont = data["continue"]


def list_photos(categories: list[str]) -> list[dict]:
    """JPEG photos in any of the categories, de-duplicated, sorted by page id."""
    pages = {}
    for category in categories:
        for page in _category_pages(category):
            # For a one-file category the API continues into the file's older uploads and
            # repeats the page; the first imageinfo it returns is the current upload.
            if page.get("imageinfo") and page["pageid"] not in pages:
                pages[page["pageid"]] = page
    out = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") != "image/jpeg":
            continue  # skip SVG/PNG diagrams, pinouts and logos
        if NOT_A_PART_PHOTO.search(page["title"].replace("_", " ")):
            continue
        meta = info.get("extmetadata", {})
        out.append({
            "pageid": page["pageid"],
            "title": page["title"],
            "page_url": info.get("descriptionurl", ""),
            "license": _strip_html(meta.get("LicenseShortName", {}).get("value", "")),
            "artist": _strip_html(meta.get("Artist", {}).get("value", "")),
            "width": info.get("width") or 0, "height": info.get("height") or 0,
            "file_url": info.get("url", "").split("?")[0],
        })
    return sorted(out, key=lambda r: r["pageid"])


def _original_url(row: dict) -> str:
    """The original file's URL; manifests written before file_url existed only kept the URL used."""
    if row.get("file_url"):
        return row["file_url"]
    used = row.get("image_url", "")
    if "/thumb/" in used:
        head, tail = used.split("/thumb/", 1)
        return f"{head}/{tail.rsplit('/', 1)[0]}"
    if used:
        return used
    name = row["title"].removeprefix("File:").replace(" ", "_")
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    return f"https://upload.wikimedia.org/wikipedia/commons/{h[0]}/{h[:2]}/{urllib.parse.quote(name)}"


def plan_from_commons(part: dict, per_part: int, per_part_sub: int) -> list[dict]:
    photos = list_photos([part["commons_category"]])[:per_part]
    if part.get("commons_subcategories"):
        seen = {p["pageid"] for p in photos}
        extra = [p for p in list_photos(part["commons_subcategories"]) if p["pageid"] not in seen]
        photos += extra[:per_part_sub]
    return photos


def plan_from_manifest(part: dict, previous: dict) -> list[dict]:
    keys = ["pageid", "title", "page_url", "license", "artist", "width", "height"]
    photos = [{**{k: r[k] for k in keys}, "file_url": _original_url(r)}
              for (pid, _), r in previous.items() if pid == part["id"]]
    for p in photos:
        p["pageid"], p["width"], p["height"] = int(p["pageid"]), int(p["width"] or 0), int(p["height"] or 0)
    return sorted(photos, key=lambda p: p["pageid"])


def _stored_size(path: Path) -> tuple[int, int] | None:
    """Size of the image at `path` if it decodes completely, else None."""
    try:
        with Image.open(path) as im:
            im.load()  # a truncated file opens fine and fails only here
            return im.size
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return None


def _is_recorded_file(path: Path, old: dict) -> bool:
    """The file on disk is the one the manifest row describes: a URL on record, the recorded
    size, and for a Commons thumbnail ("/500px-...") a width that matches the URL."""
    if not old.get("image_url") or not old.get("stored_width"):
        return False
    size = (int(old["stored_width"]), int(old["stored_height"]))
    thumb = re.search(r"/(\d+)px-[^/]*$", old["image_url"])
    if thumb and int(thumb.group(1)) != size[0]:
        return False
    return _stored_size(path) == size


def merged_manifest(previous: dict, rows: list[dict], done: set, part_ids: set) -> list[dict]:
    """This run's rows, plus every earlier row of a catalog part the run has not finished.

    Earlier rows are carried whether or not their file is on disk, so an
    interrupted run or a failed download never shrinks the dataset definition.
    Rows of parts that are no longer in parts.json are dropped.
    """
    emitted = {(r["part_id"], str(r["pageid"])) for r in rows}
    carried = [r for key, r in previous.items()
               if key[0] in part_ids and key[0] not in done and key not in emitted]
    return rows + carried


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-manifest", action="store_true",
                    help="download exactly the files listed in data/manifest.csv instead of listing Commons again")
    ap.add_argument("--per-part", type=int, default=16, help="photos from the part's own category")
    ap.add_argument("--per-part-sub", type=int, default=16, help="further photos from its part-number subcategories")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between image requests")
    args = ap.parse_args()
    if shutil.which("curl") is None:
        raise SystemExit("curl not found: it downloads the images (see download())")

    parts = json.loads((DATA / "parts.json").read_text(encoding="utf-8"))
    part_ids = {p["id"] for p in parts}
    raw = DATA / "images" / "raw"
    manifest = DATA / "manifest.csv"
    previous = {}  # rows of the last manifest
    if manifest.exists():
        with open(manifest, encoding="utf-8") as f:
            previous = {(r["part_id"], r["pageid"]): r for r in csv.DictReader(f)}
    if args.from_manifest and not previous:
        raise SystemExit(f"--from-manifest: no rows in {manifest}")
    gone = sorted({key[0] for key in previous} - part_ids)
    if gone:
        print(f"dropping manifest rows of parts no longer in parts.json: {', '.join(gone)}")
    rows, done, missing, stale = [], set(), [], []

    def save() -> None:
        tmp = manifest.with_name(manifest.name + ".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(merged_manifest(previous, rows, done, part_ids))
        tmp.replace(manifest)

    try:
        for part in parts:
            if args.from_manifest:
                photos = plan_from_manifest(part, previous)
            else:
                photos = plan_from_commons(part, args.per_part, args.per_part_sub)
            dest = raw / part["id"]
            dest.mkdir(parents=True, exist_ok=True)
            got = 0
            for p in photos:
                key = (part["id"], str(p["pageid"]))
                path = dest / f"{p['pageid']}.jpg"
                old = previous.get(key, {})
                urls = candidate_urls(p["file_url"], p["width"])
                want = None
                if args.from_manifest:
                    # Rebuild what was evaluated: only the recorded URL (today's choices when none
                    # was recorded), and only a file of the recorded size.
                    if old.get("stored_width"):
                        want = (int(old["stored_width"]), int(old["stored_height"]))
                    if old.get("image_url"):
                        urls = [old["image_url"]]
                        keep = _is_recorded_file(path, old)
                    else:
                        keep = want is not None and _stored_size(path) == want
                else:
                    # Resume only a file fetched from one of today's candidate URLs; an
                    # early 330/500px rendition or an unknown source is fetched again.
                    keep = old.get("image_url", "") in urls and _stored_size(path) is not None
                used = old.get("image_url", "") if keep else ""
                if not keep:
                    fetched, why = download(urls, path, pause=args.pause, size=want)
                    if fetched:
                        used = fetched
                    elif args.from_manifest or _stored_size(path) is None:
                        # The row stays as recorded, so a rerun retries the file. On disk there is
                        # either nothing usable or a file that is not the recorded one.
                        (stale if path.exists() else missing).append(f"{key[0]}/{key[1]} ({why})")
                        if old:
                            rows.append(old)
                        print(f"  not fetched {key[0]}/{key[1]}: {why}", flush=True)
                        continue
                    else:
                        stale.append(f"{key[0]}/{key[1]} ({why})")  # keep the older rendition and its URL
                        used = old.get("image_url", "")
                size = _stored_size(path)
                got += 1
                rows.append({"part_id": part["id"], "file": path.relative_to(DATA).as_posix(), **p, "image_url": used,
                             "stored_width": size[0], "stored_height": size[1]})
            done.add(part["id"])
            save()  # after every part, so an interrupted run still leaves a complete manifest
            print(f"{part['id']:<11} {got:2d}/{len(photos)} photos", flush=True)
    finally:
        save()
    print(f"manifest: {len(merged_manifest(previous, rows, done, part_ids))} rows, {len(missing)} files missing, "
          f"{len(stale)} not the recorded or current rendition -> {manifest}")
    for line in stale:
        print(f"  on disk but not as intended: {line}")
    if missing or stale:
        raise SystemExit(1)  # incomplete: rerun to retry these files


if __name__ == "__main__":
    main()
