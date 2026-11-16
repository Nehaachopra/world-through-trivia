"""Find a freely licensed Wikimedia Commons image for each trivia row and download it.

Usage (from the repo root):
    python scripts/fetch_images.py trivia/afghanistan.csv

For every row that has an image_search_query but no image_source_url yet, the script
searches Wikimedia Commons, keeps the first result under a free licence
(public domain, CC0, CC BY, CC BY-SA), downloads a 1200px version to the path in
image_file (e.g. images/afghanistan/buzkashi.jpg) and writes the page URL, author
and licence back into the CSV. Rows already filled in are skipped, so you can
re-run it safely, or paste in your own choice for any row and it will be left alone.
Review every picked image before publishing: the first search hit is not always right.
"""
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "WorldThroughTrivia/1.0 (https://github.com/Nehaachopra/world-through-trivia)"
FREE = re.compile(r"^(public domain|pd\b|cc0|cc[- ]by(-sa)?\b)", re.I)


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def pick_image(query: str):
    data = api({
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 10, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 1200,
    })
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        if not FREE.match(lic):
            continue
        return {
            "download": info.get("thumburl") or info.get("url"),
            "image_source_url": info.get("descriptionurl", ""),
            "image_author": strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown",
            "image_license": lic,
        }
    return None


def main(csv_path: str) -> None:
    path = Path(csv_path)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    fields = list(rows[0].keys())
    root = path.resolve().parent.parent
    for row in rows:
        q = row.get("image_search_query", "").strip()
        if not q or row.get("image_source_url"):
            continue
        try:
            hit = pick_image(q)
        except Exception as e:  # network or API hiccup: leave row for the next run
            print(f"! {q}: {e}")
            continue
        if not hit:
            print(f"- no free image found for: {q}")
            continue
        dest = root / row["image_file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(hit.pop("download"), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
        except Exception as e:
            print(f"! download failed for {q}: {e}")
            continue
        row.update(hit)
        print(f"+ {row['image_file']}  ({hit['image_license']})")
        time.sleep(1)  # be polite to Wikimedia
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1])
