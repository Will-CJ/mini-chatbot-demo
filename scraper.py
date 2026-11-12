"""Fetch the 7 PlacidWay source pages and save clean text to pages.json.

Run:  python scraper.py
The chat app reads pages.json; the app's "Refresh" button calls scrape_all() again.
"""

import json
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URLS = [
    "https://www.placidway.com/profile/5/Alternative-Cancer-Treatment-by-ITC-Immunity-Therapy-Center",
    "https://www.placidway.com/package/7903/Alternative-Adenocarcinoma-Cancer-Treatment-Package-in-Tijuana-Mexico-by-ITC",
    "https://www.placidway.com/package/7902/Alternative-Adrenal-Cancer-Treatment-Package-in-Tijuana-Mexico-by-ITC",
    "https://www.placidway.com/package/7901/Alternative-Anal-Cancer-Treatment-Package-in-Tijuana-Mexico-by-ITC",
    "https://www.placidway.com/profile-videos/5/Alternative-Cancer-Treatment-by-ITC-Immunity-Therapy-Center",
    "https://www.placidway.com/price-list/5/Alternative-Cancer-Treatment-by-ITC-Immunity-Therapy-Center",
    "https://www.placidway.com/search-medical-pricings/Alternative-Medicine/All/1",
]

ROBOTS_URL = "https://www.placidway.com/robots.txt"
# Put your own contact email here so the site owner can identify the crawler.
USER_AGENT = "PlacidWayAssessmentBot/1.0 (AI Automation assessment; contact: w1ll14m285@gmail.com)"
DELAY_SECONDS = 1.0  # about one request per second, as the brief asks
TIMEOUT_SECONDS = 20
OUT_FILE = Path(__file__).parent / "pages.json"

# Page furniture that adds noise (menus, footers, scripts, forms).
NOISE_TAGS = ["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header", "aside"]
HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
BLOCK_TAGS = ["p", "div", "li", "section", "article", "br", "dt", "dd", "tr", "ul", "ol"] + HEADING_TAGS


def load_robots(session: requests.Session) -> urllib.robotparser.RobotFileParser:
    """Download robots.txt with our own User-Agent and parse it."""
    rp = urllib.robotparser.RobotFileParser()
    resp = session.get(ROBOTS_URL, timeout=TIMEOUT_SECONDS)
    if resp.status_code == 200:
        rp.parse(resp.text.splitlines())
    elif 400 <= resp.status_code < 500:
        rp.parse([])  # no robots.txt -> everything allowed
    else:
        raise RuntimeError(f"robots.txt returned HTTP {resp.status_code}; not crawling to be safe")
    return rp


def table_to_text(table) -> str:
    """Keep price tables readable: one row per line, cells separated by ' | '."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract(html: str) -> tuple[str, str]:
    """Return (title, clean_text) for one page."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup(NOISE_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    for table in root.find_all("table"):
        table.replace_with(soup.new_string("\n" + table_to_text(table) + "\n"))
    for h in root.find_all(HEADING_TAGS):
        h.insert(0, "\n## ")
    for tag in root.find_all(BLOCK_TAGS):
        # line breaks around block elements, but not inside inline spans like "$ 5,000"
        tag.insert(0, "\n")
        tag.append("\n")

    lines = []
    for line in root.get_text().splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == "##":
            continue
        if lines and line == lines[-1]:
            continue  # drop repeated lines
        lines.append(line)
    return title, "\n".join(lines)


def scrape_all() -> dict:
    """Fetch every URL politely and return the knowledge-base dict (does not write to disk)."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    robots = load_robots(session)

    pages, errors = [], []
    for i, url in enumerate(URLS):
        if i:
            time.sleep(DELAY_SECONDS)
        if not robots.can_fetch(USER_AGENT, url):
            errors.append(f"{url}: blocked by robots.txt, skipped")
            continue
        try:
            resp = session.get(url, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as exc:
            errors.append(f"{url}: {exc}")
            continue
        title, text = extract(resp.text)
        if len(text) < 500:
            errors.append(f"{url}: only {len(text)} characters extracted; page may need JavaScript")
        pages.append({"url": url, "title": title, "text": text, "chars": len(text)})

    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages": pages,
        "errors": errors,
    }


def save(data: dict, path: Path | None = None) -> None:
    """Write atomically so the running app never reads a half-written file."""
    path = path or OUT_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    data = scrape_all()
    if not data["pages"]:
        print("No pages scraped:", *data["errors"], sep="\n  ")
        sys.exit(1)
    save(data)
    for p in data["pages"]:
        print(f"{p['chars']:>7} chars  {p['url']}")
    for e in data["errors"]:
        print("WARNING:", e)
    print(f"Saved {len(data['pages'])} pages to {OUT_FILE.name}")
