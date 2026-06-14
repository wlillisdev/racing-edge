"""
longest_travellers.py — the "longest traveller" intent signal.

A yard doesn't box a horse up and drive it hundreds of miles past nearer tracks
without confidence. This pulls the day's longest-travelling runners and flags
them on today's card, so the selector can stack travel + a consistent gamble +
an in-form stable into a "connections fancy it" read.

Source: freebets.com (free, server-scrapeable; sportsbettingtipsters.co.uk as a
fallback). The list is rendered as sentences, e.g.:
    "Trainer Jamie Snowden sends Obsessedwithyou on the 286-mile journey to
     Hexham on Saturday from his Lambourn base."

Saves data/longest_travellers_YYYY-MM-DD.json:
    {"date":..., "source":..., "travellers":[{horse,trainer,miles,course,base}]}

Run standalone to fetch + print today's list:
    python longest_travellers.py [YYYY-MM-DD]
"""

from __future__ import annotations

import re
import sys
from typing import Optional

from src.helpers import data_path, log, safe_load_json, safe_write_json, today_str

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
}

# Ordered by preference; first source that yields rows wins.
_SOURCES = [
    "https://www.freebets.com/horse-racing/longest-travellers/",
    "https://sportsbettingtipsters.co.uk/horse-racing/data/longest-travellers/",
]

# "Trainer X sends HORSE on the NNN-mile journey to COURSE [on Day] from his/her/their BASE base"
_SENTENCE = re.compile(
    r"Trainer\s+(?P<trainer>.+?)\s+sends\s+(?P<horse>.+?)\s+on\s+the\s+"
    r"(?P<miles>\d+)[-\s]?mile\s+journey\s+to\s+(?P<course>.+?)"
    r"(?:\s+on\s+\w+)?\s+from\s+(?:his|her|their)\s+(?P<base>.+?)\s+base",
    re.IGNORECASE,
)

_TAG = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    """Strip tags and collapse whitespace so the sentences parse cleanly."""
    text = _TAG.sub(" ", html)
    text = text.replace("&amp;", "&").replace("&#039;", "'").replace("&rsquo;", "'")
    return re.sub(r"\s+", " ", text)


def normalise_horse(name: str) -> str:
    """Lowercase, drop country suffix like '(FR)'/'(IRE)', keep alphanumerics —
    so 'Obsessedwithyou (FR)' (results feed) matches 'Obsessedwithyou' (list)."""
    s = re.sub(r"\(.*?\)", "", (name or "").lower())
    return re.sub(r"[^a-z0-9]", "", s)


def parse_html(html: str) -> list[dict]:
    """Extract traveller records from a longest-travellers page's HTML."""
    text = _clean(html)
    seen: set[str] = set()
    out: list[dict] = []
    for m in _SENTENCE.finditer(text):
        horse = m.group("horse").strip()
        key = normalise_horse(horse)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "horse": horse,
            "trainer": m.group("trainer").strip(),
            "miles": int(m.group("miles")),
            "course": m.group("course").strip(),
            "base": m.group("base").strip(),
        })
    return out


def fetch(date_str: Optional[str] = None) -> dict:
    """Fetch + parse the longest-travellers list, save it, and return the doc."""
    import requests  # local import — only needed when actually fetching

    date_str = date_str or today_str()
    for url in _SOURCES:
        try:
            r = requests.get(url, headers=_UA, timeout=20)
        except Exception as exc:  # noqa: BLE001 — try the next source
            log(f"longest_travellers: request error {url} — {exc}", "WARNING")
            continue
        if r.status_code != 200:
            log(f"longest_travellers: HTTP {r.status_code} from {url}", "WARNING")
            continue
        travellers = parse_html(r.text)
        if travellers:
            doc = {"date": date_str, "source": url, "travellers": travellers}
            safe_write_json(data_path(f"longest_travellers_{date_str}.json"), doc)
            log(f"longest_travellers: {len(travellers)} traveller(s) from {url}")
            return doc
        log(f"longest_travellers: 200 OK but parsed 0 rows from {url}", "WARNING")

    log("longest_travellers: no data parsed from any source", "WARNING")
    doc = {"date": date_str, "source": None, "travellers": []}
    safe_write_json(data_path(f"longest_travellers_{date_str}.json"), doc)
    return doc


def load(date_str: Optional[str] = None) -> dict:
    return safe_load_json(
        data_path(f"longest_travellers_{date_str or today_str()}.json")
    ) or {}


def traveller_for(horse_name: str, date_str: Optional[str] = None) -> Optional[dict]:
    """Return the traveller record for *horse_name* today, or None."""
    key = normalise_horse(horse_name)
    if not key:
        return None
    for t in (load(date_str).get("travellers") or []):
        if normalise_horse(t.get("horse")) == key:
            return t
    return None


def main() -> int:
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    doc = fetch(date_str)
    src = doc.get("source") or "NONE"
    travellers = doc.get("travellers") or []
    print(f"Longest travellers ({doc['date']}) — source: {src} — {len(travellers)} found")
    for t in sorted(travellers, key=lambda x: -x["miles"]):
        print(f"  {t['miles']:>4} mi  {t['horse']:<24} {t['trainer']:<20} -> "
              f"{t['course']} (from {t['base']})")
    return 0 if travellers else 1


if __name__ == "__main__":
    raise SystemExit(main())
