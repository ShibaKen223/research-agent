"""Run every configured paper source, then merge and de-duplicate the results.

Querying more than one database (Semantic Scholar + OpenAlex) is the single
biggest lever on a literature review's coverage: each database misses different
papers, so the union is far closer to "all relevant work" than either alone.

The same paper often appears in both databases, so results are de-duplicated by
DOI (falling back to a normalized title) and counted once — the report's
`## 檢索說明` appendix then records, PRISMA-style, how many records were
identified per database and how many duplicates were removed.

If one database errors (network, rate limit), the search degrades to whatever
sources did respond instead of failing outright; the failed database is recorded
in `SearchResult.failed_databases` and disclosed in the report.
"""

from collections.abc import Sequence
from dataclasses import asdict

from research_agent import cache, openalex
from research_agent.semantic_scholar import SOURCE as S2_SOURCE
from research_agent.semantic_scholar import SearchResult
from research_agent.semantic_scholar import search_papers as s2_search
from research_agent.text_utils import normalize_title


class SearchError(RuntimeError):
    """Raised only when *every* configured source failed."""


# name -> (runner, human label). Order here is the relevance-interleave order.
_SOURCES = {
    "semantic_scholar": (s2_search, S2_SOURCE),
    "openalex": (openalex.search_papers, openalex.SOURCE),
}
DEFAULT_DATABASES = ("semantic_scholar", "openalex")


def search(
    query: str | Sequence[str],
    limit: int = 20,
    sort: str = "relevance",
    min_citations: int = 0,
    year_from: int | None = None,
    databases: tuple[str, ...] = DEFAULT_DATABASES,
) -> SearchResult:
    """Search every database in `databases` for every query string in `query`,
    then merge, de-duplicate, and return one combined `SearchResult`.

    `query` may be a single string or several — passing both a Chinese keyword
    *and* its English translation ("dual-querying") widens coverage for the
    English-dominated corpora. Each (query, source) pair is fetched for `limit`,
    so the merged pool is at least as deep as a single-source search before
    truncation. Results are cached on (queries, params), so an identical re-run
    is instant and doesn't re-hit the rate-limited APIs."""
    queries = [query] if isinstance(query, str) else [q for q in query if q and q.strip()]
    if not queries:
        raise SearchError("沒有可用的檢索式。")

    ck = cache.key("search", queries, limit, sort, min_citations, year_from, list(databases))
    hit = cache.get("search", ck)
    if hit is not None:
        return SearchResult(**hit)

    results: list[SearchResult] = []
    succeeded: list[str] = []
    failed: list[str] = []
    for q in queries:
        for name in databases:
            runner, label = _SOURCES[name]
            try:
                results.append(
                    runner(
                        q,
                        limit=limit,
                        sort=sort,
                        min_citations=min_citations,
                        year_from=year_from,
                    )
                )
                succeeded.append(label)
            except Exception:  # noqa: BLE001 — one dead source must not sink the search
                failed.append(label)

    if not results:
        raise SearchError("所有文獻資料庫都查詢失敗，請稍後再試。")

    # A source only counts as failed if it never succeeded for *any* query.
    failed = [f for f in dict.fromkeys(failed) if f not in succeeded]
    merged = _merge(results, sort=sort, limit=limit, failed=failed)
    cache.set("search", ck, asdict(merged))
    return merged


def _merge(
    results: list[SearchResult], *, sort: str, limit: int, failed: list[str]
) -> SearchResult:
    total = 0
    have_total = False
    fetched = excluded_no_abstract = excluded_by_filter = 0
    databases: list[str] = []
    for r in results:
        if r.total_matches is not None:
            total += r.total_matches
            have_total = True
        fetched += r.fetched
        excluded_no_abstract += r.excluded_no_abstract
        excluded_by_filter += r.excluded_by_filter
        databases += r.databases
    # The same database appears once per query when dual-querying; list it once.
    databases = list(dict.fromkeys(databases))

    lists = [list(r.papers) for r in results]
    if sort == "citations":
        ordered = sorted(
            (p for lst in lists for p in lst),
            key=lambda p: p.get("citation_count") or 0,
            reverse=True,
        )
    else:
        ordered = _interleave(lists)

    deduped, duplicates = _dedup(ordered)
    final = deduped[:limit]

    contributions: dict[str, int] = {}
    for p in final:
        label = p.get("source") or "?"
        contributions[label] = contributions.get(label, 0) + 1

    return SearchResult(
        papers=final,
        total_matches=total if have_total else None,
        fetched=fetched,
        excluded_no_abstract=excluded_no_abstract,
        excluded_by_filter=excluded_by_filter,
        excluded_duplicates=duplicates,
        sources=contributions,
        databases=databases,
        failed_databases=failed,
    )


def _interleave(lists: list[list[dict]]) -> list[dict]:
    """Round-robin the per-source relevance rankings so neither database
    dominates the top of the merged list before truncation."""
    out: list[dict] = []
    i = 0
    while any(i < len(lst) for lst in lists):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
        i += 1
    return out


def _dedup(papers: list[dict]) -> tuple[list[dict], int]:
    """Drop papers already seen (same DOI, or same normalized title when a DOI
    is absent), preserving order. Returns (kept, removed_count)."""
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    kept: list[dict] = []
    removed = 0
    for p in papers:
        doi = p.get("doi") or ""
        title_key = normalize_title(p.get("title"))
        if (doi and doi in seen_doi) or (title_key and title_key in seen_title):
            removed += 1
            continue
        kept.append(p)
        if doi:
            seen_doi.add(doi)
        if title_key:
            seen_title.add(title_key)
    return kept, removed
