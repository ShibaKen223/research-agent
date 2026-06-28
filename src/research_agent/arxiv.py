"""Search papers via the arXiv API (no API key required).

arXiv is the primary preprint server for physics, maths, CS, quantitative
biology/finance and statistics. Adding it as a third source alongside Semantic
Scholar and OpenAlex surfaces very recent work — preprints often appear here
months before a journal publishes them or a citation database indexes them —
which is exactly the coverage a review of a fast-moving field is most likely to
miss.

The arXiv API returns an Atom XML feed (not JSON), so `_parse_feed` turns it into
the same normalized paper dicts / `SearchResult` shape the other sources emit and
the orchestrator merges all three uniformly. arXiv exposes no citation counts, so
`citation_count` is always 0 and a `min_citations` floor makes arXiv contribute
nothing — a preprint server can't certify citation impact (see `search_papers`).
"""

import time
import xml.etree.ElementTree as ET

import requests

from research_agent.semantic_scholar import SearchResult
from research_agent.text_utils import normalize_doi

API_URL = "https://export.arxiv.org/api/query"
SOURCE = "arXiv"
MAX_RETRIES = 4
HEADERS = {"User-Agent": "research-agent/0.1.0 (https://github.com/research-agent)"}

# Namespaces used in the arXiv Atom feed.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


class ArxivError(RuntimeError):
    pass


def search_papers(
    query: str,
    limit: int = 20,
    sort: str = "relevance",
    min_citations: int = 0,
    year_from: int | None = None,
) -> SearchResult:
    """Search arXiv for papers matching `query`.

    Mirrors the other sources' signature and return shape, with two
    arXiv-specific quirks:

    - arXiv has no citation data. `sort="citations"` therefore can't be honored
      at the source — we fetch newest-first and let the cross-source merge
      re-rank by `citation_count` (arXiv's, all 0, simply sort after the indexed
      papers). And a `min_citations >= 1` floor excludes arXiv entirely, since a
      preprint's "0 citations" means *unknown*, not *zero* — so we skip the call
      and return an empty result rather than fetching papers that can't qualify.
    - `year_from` is pushed server-side (a submittedDate range) *and* re-checked
      client-side, as the other sources do with their own filters.
    """
    if min_citations:
        return SearchResult(sources={SOURCE: 0}, databases=[SOURCE])

    search_query = f"all:{query}"
    if year_from is not None:
        # arXiv date filter: submittedDate:[YYYYMMDDhhmm TO YYYYMMDDhhmm].
        search_query += f" AND submittedDate:[{year_from}01010000 TO 209912312359]"

    params = {
        "search_query": search_query,
        "start": 0,
        # Over-fetch, because the client-side year re-check below can drop some.
        "max_results": min(max(limit * 2, 10), 100),
        # arXiv can't sort by citations; newest-first is the sensible fallback
        # there (the merge re-ranks anyway). Otherwise use relevance.
        "sortBy": "submittedDate" if sort == "citations" else "relevance",
        "sortOrder": "descending",
    }

    normalized, total = _parse_feed(_get(params))
    fetched = len(normalized)

    with_abstract = [p for p in normalized if p["abstract"]]
    before_filter = len(with_abstract)
    papers = with_abstract
    if year_from is not None:
        papers = [p for p in papers if (p["year"] or 0) >= year_from]

    final = papers[:limit]
    return SearchResult(
        papers=final,
        total_matches=total,
        fetched=fetched,
        excluded_no_abstract=fetched - len(with_abstract),
        excluded_by_filter=before_filter - len(papers),
        sources={SOURCE: len(final)},
        databases=[SOURCE],
    )


def _get(params: dict) -> str:
    """GET the Atom feed with 429/503 backoff (honoring Retry-After), raising
    ArxivError on a non-2xx response so the orchestrator can treat arXiv as a
    failed source. arXiv signals overload with 503 and asks clients to back off."""
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        if resp.status_code not in (429, 503):
            break
        if attempt == MAX_RETRIES:
            raise ArxivError("arXiv rate limit hit repeatedly, please retry later.")
        wait = float(resp.headers.get("Retry-After", 2**attempt))
        time.sleep(wait)

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise ArxivError(f"arXiv API error: {e}") from e
    return resp.text


def _clean(text: str | None) -> str:
    """Collapse the newlines/indentation arXiv wraps titles and abstracts in."""
    return " ".join((text or "").split())


def _parse_feed(xml_text: str) -> tuple[list[dict], int | None]:
    """Parse an arXiv Atom feed into (normalized paper dicts, total_matches).

    Pure and offline so it can be unit-tested without the network. A malformed
    feed raises ArxivError (caught upstream as a source failure)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ArxivError(f"arXiv returned an unparseable feed: {e}") from e

    total = None
    total_el = root.find("opensearch:totalResults", _NS)
    if total_el is not None and (total_el.text or "").strip().isdigit():
        total = int(total_el.text.strip())

    papers = [_normalize(e) for e in root.findall("atom:entry", _NS)]
    return papers, total


def _normalize(entry: ET.Element) -> dict:
    id_url = (entry.findtext("atom:id", default="", namespaces=_NS) or "").strip()
    arxiv_id = id_url.rsplit("/abs/", 1)[-1] if "/abs/" in id_url else id_url
    published = entry.findtext("atom:published", default="", namespaces=_NS) or ""
    year = int(published[:4]) if published[:4].isdigit() else None
    authors = [
        _clean(a.findtext("atom:name", default="", namespaces=_NS))
        for a in entry.findall("atom:author", _NS)
    ]
    journal_ref = _clean(entry.findtext("arxiv:journal_ref", default="", namespaces=_NS))
    return {
        "title": _clean(entry.findtext("atom:title", default="", namespaces=_NS)) or "Untitled",
        "authors": [a for a in authors if a],
        "year": year,
        "abstract": _clean(entry.findtext("atom:summary", default="", namespaces=_NS)),
        "url": id_url,
        # A preprint's venue is arXiv itself unless it carries a published-in ref.
        "venue": journal_ref or SOURCE,
        "citation_count": 0,  # arXiv exposes no citation data
        "doi": normalize_doi(entry.findtext("arxiv:doi", default="", namespaces=_NS)),
        "paper_id": arxiv_id,
        "source": SOURCE,
    }
