"""Taiwan master's/PhD thesis cross-check (題目對照) via official open data.

The abstract-based pipeline (Semantic Scholar / OpenAlex / arXiv) has almost no
coverage of Chinese-language Taiwan theses, so its 研究缺口 / 碩論題目建議 can miss
that a topic has *already been done* — a dangerous false negative for a Taiwanese
master's student judging novelty.

This module closes that gap with the **official open data** of 國家圖書館's 臺灣博碩士
論文知識加值系統 (data.gov.tw dataset 14024): per-academic-year CSVs under the
Government Open Data License. It downloads (and disk-caches) the recent years,
matches the keyword against thesis **titles**, and reuses the Haiku relevance gate
(`relevance.filter_by_relevance`) to keep only the topically relevant ones — shown
in a dedicated 「臺灣碩博士論文對照」 report section.

Hard limits to be honest about: the open data has **no abstracts/keywords**, so
this is title-only (it can flag that similar theses exist, not analyse them); and
to bound the download it only covers the most recent few academic years. It is
opt-in, and **never merged into the abstract-based analysis** (a title-only record
would poison the relevance/claim checks). Fail-open throughout: a failed download
or scoring degrades to "skipped"/"unscored", never raising.
"""

import csv
import io
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests

OPENDATA_URL = "https://ndltd.ncl.edu.tw/opendata/{year}ndltd.csv"
HEADERS = {"User-Agent": "research-agent/0.1.0 (https://github.com/research-agent)"}
_HTTP_TIMEOUT = 120

# Bounds. Only the most recent few academic years are fetched (each CSV is ~18 MB);
# only this many title matches are scored by Haiku; only this many are shown.
MAX_YEARS = 3
MAX_CANDIDATES = 60
DISPLAY_MAX = 25
_YEAR_LOOKBACK = 6  # how many ROC years back to *try* (newest first) to find MAX_YEARS


@dataclass
class ThesisCrossCheckResult:
    checked: bool = True  # False when no CSV could be downloaded at all
    theses: list[dict] = field(default_factory=list)  # relevant theses, capped
    matched: int = 0  # how many titles matched the keyword before scoring
    scored: bool = False  # whether Haiku relevance scoring actually ran
    years: list[int] = field(default_factory=list)  # ROC academic years searched


def search_theses(keyword: str, years: list[int] | None = None) -> ThesisCrossCheckResult:
    """Cross-check `keyword` against recent Taiwan thesis titles. Returns a
    `ThesisCrossCheckResult`; never raises. `checked=False` only if no open-data CSV
    could be fetched at all."""
    terms = _terms(keyword)
    if not terms:
        return ThesisCrossCheckResult(checked=False)

    candidates: list[dict] = []
    matched = 0
    searched: list[int] = []
    for year in years or _candidate_years():
        if len(searched) >= MAX_YEARS:
            break
        text = _load_year(year)
        if text is None:
            continue
        searched.append(year)
        for thesis in _iter_theses(text):
            score = _match_score(thesis, terms)
            if score > 0:
                matched += 1
                thesis["_match"] = score
                candidates.append(thesis)

    if not searched:
        return ThesisCrossCheckResult(checked=False, years=[])
    if not candidates:
        return ThesisCrossCheckResult(checked=True, theses=[], matched=0, years=searched)

    candidates.sort(key=lambda t: (t.get("_match", 0), _year_int(t)), reverse=True)
    capped = candidates[:MAX_CANDIDATES]

    # Reuse the proven Haiku relevance gate to score titles (imported lazily so this
    # module stays importable — and its pure helpers testable — without anthropic).
    from research_agent.relevance import filter_by_relevance

    rel = filter_by_relevance(keyword, capped)
    if not rel.checked:
        kept, scored = capped, False  # couldn't score: show matches, flagged unscored
    elif rel.inconclusive:
        kept, scored = [], True  # scored but none clearly relevant = a real "no" here
    else:
        kept, scored = rel.kept, True

    for t in kept:
        t.pop("_match", None)
    return ThesisCrossCheckResult(
        checked=True, theses=kept[:DISPLAY_MAX], matched=matched, scored=scored, years=searched
    )


# --- keyword / title matching (pure) -----------------------------------------

def _terms(keyword: str) -> list[str]:
    """Whitespace-split search terms (>=2 chars), lowercased so English matching is
    case-insensitive (Chinese is unaffected)."""
    return [t for t in (keyword or "").lower().split() if len(t) >= 2]


def _match_score(thesis: dict, terms: list[str]) -> int:
    """How many distinct keyword terms appear in the thesis's (Chinese+foreign)
    title. 0 = no match. Used to rank candidates before Haiku scoring."""
    hay = (f"{thesis.get('title', '')} {thesis.get('title_en', '')}").lower()
    return sum(1 for t in terms if t in hay)


def _year_int(thesis: dict) -> int:
    y = "".join(ch for ch in (thesis.get("year") or "") if ch.isdigit())
    return int(y) if y else 0


# --- CSV parsing (pure) ------------------------------------------------------

# Map the open data's Chinese column headers to stable keys by substring, so a
# minor rename or column reorder doesn't silently break parsing.
def _header_index(header: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, raw in enumerate(header):
        h = (raw or "").strip().lstrip("\ufeff")
        if "論文名稱" in h and "外文" in h:
            idx["title_en"] = i
        elif "論文名稱" in h or ("title" in h.lower() and "en" not in h.lower()):
            idx.setdefault("title", i)
        elif "學校" in h:
            idx["school"] = i
        elif "系所" in h:
            idx["dept"] = i
        elif "學年" in h:
            idx["year"] = i
        elif "學位" in h:
            idx["degree"] = i
        elif "指導" in h:
            idx["advisor"] = i
        elif "作者" in h:
            idx["author"] = i
        elif "網址" in h or "url" in h.lower():
            idx["url"] = i
    return idx


def _iter_theses(text: str):
    """Yield normalized thesis dicts from one year's CSV text. Skips rows that don't
    line up with the header. Pure/offline (unit-tested)."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return
    idx = _header_index(header)
    if "title" not in idx:
        return
    for row in reader:
        if not row:
            continue
        yield {key: row[i].strip() for key, i in idx.items() if i < len(row)}


# --- download + disk cache ---------------------------------------------------

def _candidate_years() -> list[int]:
    """ROC academic years to try, newest first. `NDLTD_YEARS` (comma list) overrides;
    otherwise the last few from the current ROC year — non-existent recent years just
    404 and are skipped, so this auto-adapts as new years are published."""
    env = os.environ.get("NDLTD_YEARS")
    if env:
        return [int(x) for x in env.split(",") if x.strip().isdigit()]
    latest = date.today().year - 1911
    return list(range(latest, latest - _YEAR_LOOKBACK, -1))


def _cache_dir() -> Path:
    base = os.environ.get("RESEARCH_AGENT_CACHE_DIR", ".research_agent_cache")
    d = Path(base) / "ndltd"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_year(year: int) -> str | None:
    """One year's CSV text, from the disk cache if present (the data updates only
    annually), else downloaded and cached. None on any failure."""
    path = _cache_dir() / f"{year}ndltd.csv"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8-sig")
        except OSError:
            pass
    text = _fetch_year(year)
    if text is None:
        return None
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


def _fetch_year(year: int) -> str | None:
    try:
        resp = requests.get(
            OPENDATA_URL.format(year=year), headers=HEADERS, timeout=_HTTP_TIMEOUT
        )
        if resp.status_code != 200:
            return None
        resp.encoding = "utf-8-sig"
        return resp.text
    except requests.RequestException:
        return None
