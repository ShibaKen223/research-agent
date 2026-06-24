"""Search papers via the OpenAlex API (no API key required).

OpenAlex indexes ~250M scholarly works across every discipline. Adding it as a
second source alongside Semantic Scholar widens coverage and reduces the
single-database bias that is the biggest threat to a literature review's
validity. Set the env var `OPENALEX_MAILTO` to join OpenAlex's faster "polite
pool"; it is optional and never required.

Unlike Semantic Scholar, OpenAlex returns abstracts as an inverted index
(word -> positions) for copyright reasons, so `_reconstruct_abstract` rebuilds
the plain text. Results are returned as the same `SearchResult` shape as
`semantic_scholar.search_papers`, so the orchestrator can merge them uniformly.
"""

import os
import time

import requests

from research_agent.semantic_scholar import SearchResult
from research_agent.text_utils import normalize_doi

WORKS_URL = "https://api.openalex.org/works"
# Only pull the fields we use, to keep the (otherwise large) response small.
SELECT = (
    "id,doi,title,display_name,publication_year,authorships,"
    "abstract_inverted_index,primary_location,cited_by_count,ids"
)
SOURCE = "OpenAlex"
MAX_RETRIES = 4


class OpenAlexError(RuntimeError):
    pass


def search_papers(
    query: str,
    limit: int = 20,
    sort: str = "relevance",
    min_citations: int = 0,
    year_from: int | None = None,
) -> SearchResult:
    """Search OpenAlex for works matching `query`.

    Mirrors `semantic_scholar.search_papers`: `sort="citations"` orders by
    `cited_by_count` desc server-side; otherwise OpenAlex's relevance ranking is
    used. Year/citation filters are pushed server-side and re-checked locally.
    Papers without a reconstructable abstract are excluded (and counted).
    """
    params = {
        "search": query,
        "select": SELECT,
        # Over-fetch, because works without an abstract get filtered out below.
        "per-page": min(max(limit * 2, 10), 100),
    }

    filters = []
    if year_from is not None:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if min_citations:
        filters.append(f"cited_by_count:>{min_citations - 1}")
    if filters:
        params["filter"] = ",".join(filters)

    if sort == "citations":
        params["sort"] = "cited_by_count:desc"

    mailto = os.environ.get("OPENALEX_MAILTO")
    if mailto:
        params["mailto"] = mailto

    data = _get(WORKS_URL, params)
    rows = data.get("results") or []
    fetched = len(rows)

    normalized = [_normalize(r) for r in rows]
    with_abstract = [p for p in normalized if p["abstract"]]

    # Re-check client-side too, in case the API's filtering ever disagrees.
    before_filter = len(with_abstract)
    papers = with_abstract
    if year_from is not None:
        papers = [p for p in papers if (p["year"] or 0) >= year_from]
    if min_citations:
        papers = [p for p in papers if p["citation_count"] >= min_citations]

    final = papers[:limit]
    meta = data.get("meta") or {}
    return SearchResult(
        papers=final,
        total_matches=meta.get("count"),
        fetched=fetched,
        excluded_no_abstract=fetched - len(with_abstract),
        excluded_by_filter=before_filter - len(papers),
        sources={SOURCE: len(final)},
        databases=[SOURCE],
    )


def _get(url: str, params: dict) -> dict:
    """GET with 429 backoff (honoring Retry-After), raising OpenAlexError on a
    non-2xx response so the orchestrator can treat this source as failed."""
    headers = {"User-Agent": _user_agent()}
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code != 429:
            break
        if attempt == MAX_RETRIES:
            raise OpenAlexError("OpenAlex rate limit hit repeatedly, please retry later.")
        wait = float(resp.headers.get("Retry-After", 2**attempt))
        time.sleep(wait)

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise OpenAlexError(f"OpenAlex API error: {e}") from e
    return resp.json()


def _user_agent() -> str:
    ua = "research-agent/0.1.0"
    mailto = os.environ.get("OPENALEX_MAILTO")
    return f"{ua} (mailto:{mailto})" if mailto else ua


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """Rebuild plain abstract text from OpenAlex's {word: [positions]} index."""
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(word for _, word in positions)


def _normalize(work: dict) -> dict:
    doi = work.get("doi")
    primary = work.get("primary_location") or {}
    source_obj = primary.get("source") or {}
    url = primary.get("landing_page_url") or doi or work.get("id") or ""
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in work.get("authorships") or []
    ]
    return {
        "title": work.get("display_name") or work.get("title") or "Untitled",
        "authors": [a for a in authors if a],
        "year": work.get("publication_year"),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "url": url,
        "venue": source_obj.get("display_name") or "",
        "citation_count": work.get("cited_by_count") or 0,
        "doi": normalize_doi(doi),
        "paper_id": (work.get("ids") or {}).get("openalex") or work.get("id") or "",
        "source": SOURCE,
    }
