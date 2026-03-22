"""
scrape_ghibli_scripts.py
------------------------
Scrapes all available English screenplay scripts for Studio Ghibli films
from https://www.nausicaa.net/wiki/

Strategy:
  1. Fetch the "Scripts and lyrics" category page to discover all film
     script pages.
  2. For each film's "(scripts and lyrics)" wiki page, find .txt links
     that look like English scripts.
  3. Download each .txt file and save it locally under ./ghibli_scripts/.

Usage:
  python scrape_ghibli_scripts.py

Output:
  ./ghibli_scripts/<Film Title>/<filename>.txt
"""

import re
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_WIKI   = "https://www.nausicaa.net/wiki/"
BASE_SITE   = "https://www.nausicaa.net"
CATEGORY    = "https://www.nausicaa.net/wiki/Category:Scripts_and_lyrics"
OUTPUT_DIR  = Path("ghibli_scripts")
DELAY       = 1.5   # seconds between requests — be polite to the server

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GhibliScriptScraper/1.0; "
        "educational research project)"
    )
}

# Keywords that indicate a link is an English script (case-insensitive).
# We require at least one of these to appear in the href or link text,
# AND the file must end in .txt.
ENGLISH_HINTS = [
    "english", "_en_", "_en.", "-en-", "-en.", "english_", "eng_", "eng.",
]

# Keywords that mark a link as definitely NOT the screenplay text
# (e.g. TeX source, lyrics, subtitles).
EXCLUDE_HINTS = [
    "tex", "lyric", "subtitle", "spanish", "french", "italian",
    "german", "japanese", "portuguese", "dutch",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(url: str) -> requests.Response:
    """GET with retries and polite delay."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            time.sleep(DELAY)
            return resp
        except requests.RequestException as exc:
            print(f"  ⚠ Attempt {attempt + 1} failed for {url}: {exc}")
            time.sleep(DELAY * 2)
    raise RuntimeError(f"Failed to fetch {url} after 3 attempts")


def safe_dirname(title: str) -> str:
    """Turn a film title into a safe directory name."""
    title = re.sub(r'[\\/*?:"<>|]', "", title)
    title = title.strip().replace("  ", " ")
    return title


def is_english_script(href: str, text: str) -> bool:
    """Return True if this .txt link looks like an English screenplay."""
    combined = (href + " " + text).lower()

    # Must be a .txt file
    if not href.lower().endswith(".txt"):
        return False

    # Must not be a clearly excluded type
    if any(ex in combined for ex in EXCLUDE_HINTS):
        return False

    # Must contain an English hint OR be the only .txt on the page
    # (we handle the "only .txt" case in the caller)
    if any(hint in combined for hint in ENGLISH_HINTS):
        return True

    return False


# ---------------------------------------------------------------------------
# Core scraping
# ---------------------------------------------------------------------------

def get_script_pages() -> list[tuple[str, str]]:
    """
    Fetch the Scripts & Lyrics category page and return a list of
    (film_title, wiki_url) for every film script page (skipping song pages).
    """
    print("Fetching category index …")
    soup = BeautifulSoup(get(CATEGORY).text, "html.parser")
    pages = []

    for a in soup.select("div.mw-category a, #mw-pages a"):
        title = a.get_text(strip=True)
        href  = a.get("href", "")

        # Keep only film script pages (not individual song pages)
        if "(scripts and lyrics)" not in title:
            continue

        url = BASE_SITE + href if href.startswith("/") else href
        film_title = title.replace("(scripts and lyrics)", "").strip()
        pages.append((film_title, url))
        print(f"  Found: {film_title}")

    return pages


def find_english_script_urls(film_title: str, wiki_url: str) -> list[tuple[str, str]]:
    """
    Fetch a film's scripts-and-lyrics wiki page and return a list of
    (label, absolute_url) for English .txt script files.
    """
    print(f"\n  Scanning: {wiki_url}")
    soup = BeautifulSoup(get(wiki_url).text, "html.parser")

    # Collect all .txt hrefs on the page
    all_txt_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if href.lower().endswith(".txt"):
            abs_url = (
                BASE_SITE + href if href.startswith("/") else href
            )
            all_txt_links.append((text, href, abs_url))

    if not all_txt_links:
        print("    No .txt links found.")
        return []

    # Filter to English scripts
    english = [
        (text, abs_url)
        for text, href, abs_url in all_txt_links
        if is_english_script(href, text)
    ]

    # Fallback: if no link matched English hints but there's exactly one
    # .txt and it isn't in the exclude list, assume it's the English script.
    if not english and len(all_txt_links) == 1:
        text, href, abs_url = all_txt_links[0]
        combined = (href + " " + text).lower()
        if not any(ex in combined for ex in EXCLUDE_HINTS):
            english = [(text, abs_url)]

    for text, url in english:
        print(f"    ✓ English script: {text or url.split('/')[-1]}")

    if not english:
        print("    (No English script identified among .txt links.)")

    return english


def download_scripts(film_title: str, script_links: list[tuple[str, str]]) -> None:
    """Download and save each script file."""
    if not script_links:
        return

    out_dir = OUTPUT_DIR / safe_dirname(film_title)
    out_dir.mkdir(parents=True, exist_ok=True)

    for label, url in script_links:
        filename = url.split("/")[-1]
        dest = out_dir / filename

        if dest.exists():
            print(f"    Already downloaded: {filename}")
            continue

        print(f"    Downloading {filename} …")
        try:
            resp = get(url)
            # Try to decode as UTF-8, fall back to latin-1
            try:
                text = resp.content.decode("utf-8")
            except UnicodeDecodeError:
                text = resp.content.decode("latin-1")

            dest.write_text(text, encoding="utf-8")
            print(f"    Saved → {dest}  ({len(text):,} chars)")
        except Exception as exc:
            print(f"    ✗ Failed to download {url}: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR.resolve()}\n")

    # Step 1: discover all film script pages
    script_pages = get_script_pages()
    print(f"\nFound {len(script_pages)} film script pages.\n{'─' * 60}")

    summary: list[tuple[str, int]] = []

    # Step 2 & 3: for each film, find and download English scripts
    for film_title, wiki_url in script_pages:
        english_links = find_english_script_urls(film_title, wiki_url)
        download_scripts(film_title, english_links)
        summary.append((film_title, len(english_links)))

    # Final summary
    print(f"\n{'─' * 60}")
    print("Summary")
    print(f"{'─' * 60}")
    total = 0
    for film, count in summary:
        status = f"{count} script(s)" if count else "— no English script found"
        print(f"  {film:<45} {status}")
        total += count
    print(f"{'─' * 60}")
    print(f"  Total scripts downloaded: {total}")
    print(f"  Saved to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
