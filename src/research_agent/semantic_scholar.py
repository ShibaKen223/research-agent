"""Search papers via the Semantic Scholar Graph API (no API key required)."""

import time

import requests

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,year,abstract,url,venue,citationCount"
MAX_RETRIES = 4
HEADERS = {"User-Agent": "research-agent/0.1.0 (https://github.com/research-agent)"}


class SemanticScholarError(RuntimeError):
    pass


def search_papers(query: str, limit: int = 20) -> list[dict]:
    """Search Semantic Scholar for papers matching `query`, newest-first by relevance.

    The key-less endpoint shares a tight public rate limit, so 429s are retried
    with backoff (honoring Retry-After when present) before giving up.
    """
    params = {"query": query, "limit": limit, "fields": FIELDS}

    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        if resp.status_code != 429:
            break
        if attempt == MAX_RETRIES:
            raise SemanticScholarError(
                "Semantic Scholar rate limit hit repeatedly, please retry later."
            )
        wait = float(resp.headers.get("Retry-After", 2 ** attempt))
        time.sleep(wait)

    resp.raise_for_status()
    data = resp.json()
    papers = data.get("data", [])
    return [_normalize(p) for p in papers if p.get("abstract")]


def _normalize(paper: dict) -> dict:
    return {
        "title": paper.get("title") or "Untitled",
        "authors": [a.get("name", "") for a in paper.get("authors") or []],
        "year": paper.get("year"),
        "abstract": paper.get("abstract") or "",
        "url": paper.get("url") or "",
        "venue": paper.get("venue") or "",
        "citation_count": paper.get("citationCount") or 0,
    }
