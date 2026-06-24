"""Search papers via the Semantic Scholar Graph API (no API key required)."""

import time
from dataclasses import dataclass, field

import requests

from research_agent.text_utils import normalize_doi

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
BULK_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = "paperId,title,authors,year,abstract,url,venue,citationCount,externalIds"
SOURCE = "Semantic Scholar"
MAX_RETRIES = 4
HEADERS = {"User-Agent": "research-agent/0.1.0 (https://github.com/research-agent)"}


class SemanticScholarError(RuntimeError):
    pass


@dataclass
class SearchResult:
    """Papers plus the provenance counts needed for a reproducible search record.

    `papers` is the final included list (capped at `limit`). The counts let the
    report state, PRISMA-style, how many papers were found vs. excluded and why,
    instead of silently dropping them.
    """

    papers: list[dict] = field(default_factory=list)
    total_matches: int | None = None  # API's estimate of all corpus matches for the query
    fetched: int = 0  # rows actually pulled back from the API
    excluded_no_abstract: int = 0  # of `fetched`, dropped for having no abstract
    excluded_by_filter: int = 0  # of those, dropped by the year/citation re-check
    excluded_duplicates: int = 0  # dropped because another source already had the paper
    sources: dict[str, int] = field(default_factory=dict)  # included papers per database
    databases: list[str] = field(default_factory=list)  # databases queried successfully
    failed_databases: list[str] = field(default_factory=list)  # queried but errored out

    def __bool__(self) -> bool:  # so callers can keep writing `if not result:`
        return bool(self.papers)


def search_papers(
    query: str,
    limit: int = 20,
    sort: str = "relevance",
    min_citations: int = 0,
    year_from: int | None = None,
) -> SearchResult:
    """Search Semantic Scholar for papers matching `query`.

    `sort="relevance"` (default) uses the keyword-relevance endpoint, capped at
    100 results. `sort="citations"` uses the bulk endpoint with server-side
    `sort=citationCount:desc`, so the highest-cited papers in the whole corpus
    come back first — not just a re-ranking of a small relevance-ranked page.

    Returns a `SearchResult` carrying both the included papers and the counts of
    what was found and excluded, so the report can document the search.
    """
    if sort == "citations":
        url = BULK_SEARCH_URL
        params = {"query": query, "fields": FIELDS, "sort": "citationCount:desc"}
    else:
        url = SEARCH_URL
        # Papers without an abstract get filtered out below, so over-fetch to
        # still land near `limit` results after filtering.
        params = {"query": query, "limit": min(limit * 2, 100), "fields": FIELDS}

    # Push these server-side too: on the bulk endpoint especially, this shrinks
    # the (otherwise uncapped, up to 1000-paper) result page instead of fetching
    # everything and filtering client-side.
    if min_citations:
        params["minCitationCount"] = min_citations
    if year_from is not None:
        params["year"] = f"{year_from}-"

    data = _get(url, params)
    rows = data.get("data") or []
    fetched = len(rows)

    with_abstract = [p for p in rows if p.get("abstract")]
    papers = [_normalize(p) for p in with_abstract]

    # Re-check client-side too, in case the API's own filtering ever disagrees
    # with what we asked for.
    before_filter = len(papers)
    if year_from is not None:
        papers = [p for p in papers if (p["year"] or 0) >= year_from]
    if min_citations:
        papers = [p for p in papers if p["citation_count"] >= min_citations]

    final = papers[:limit]
    return SearchResult(
        papers=final,
        total_matches=data.get("total"),
        fetched=fetched,
        excluded_no_abstract=fetched - len(with_abstract),
        excluded_by_filter=before_filter - len(papers),
        sources={SOURCE: len(final)},
        databases=[SOURCE],
    )


def _get(url: str, params: dict) -> dict:
    """GET with 429 backoff (honoring Retry-After), raising SemanticScholarError
    on a non-2xx response so callers don't need to catch raw requests errors."""
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if resp.status_code != 429:
            break
        if attempt == MAX_RETRIES:
            raise SemanticScholarError(
                "Semantic Scholar rate limit hit repeatedly, please retry later."
            )
        wait = float(resp.headers.get("Retry-After", 2**attempt))
        time.sleep(wait)

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise SemanticScholarError(f"Semantic Scholar API error: {e}") from e
    return resp.json()


def _normalize(paper: dict) -> dict:
    external = paper.get("externalIds") or {}
    return {
        "title": paper.get("title") or "Untitled",
        "authors": [a.get("name", "") for a in paper.get("authors") or []],
        "year": paper.get("year"),
        "abstract": paper.get("abstract") or "",
        "url": paper.get("url") or "",
        "venue": paper.get("venue") or "",
        "citation_count": paper.get("citationCount") or 0,
        "doi": normalize_doi(external.get("DOI")),
        "paper_id": paper.get("paperId") or "",
        "source": SOURCE,
    }
