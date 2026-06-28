"""Offline unit tests for the multi-source merge/dedup and the verify gate.

No network and no Claude calls: every test uses hand-built data. Runs under
pytest (`pytest tests/`) or as a plain script (`python tests/test_dedup_and_verify.py`)
so it works even without pytest installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import cache, openalex, sources  # noqa: E402
from research_agent.semantic_scholar import SearchResult  # noqa: E402
from research_agent.text_utils import normalize_doi, normalize_title  # noqa: E402
from research_agent.verify import verify_matrix  # noqa: E402

# These tests are offline and deterministic; the on-disk cache would otherwise
# serve a stale result when the same query is searched twice (e.g. the source-
# failure test) and write files into the working directory.
cache.disable()


def _paper(title, doi="", source="Semantic Scholar", citation_count=0):
    return {
        "title": title,
        "authors": [],
        "year": 2020,
        "abstract": "x",
        "url": "",
        "venue": "",
        "citation_count": citation_count,
        "doi": normalize_doi(doi),
        "paper_id": "",
        "source": source,
    }


# --- text_utils ---------------------------------------------------------------

def test_normalize_doi_strips_url_and_case():
    assert normalize_doi("https://doi.org/10.1/AbC") == "10.1/abc"
    assert normalize_doi(None) == ""


def test_normalize_title_folds_punctuation():
    assert normalize_title("Deep Learning: A Survey!") == "deep learning a survey"


# --- openalex abstract reconstruction ----------------------------------------

def test_reconstruct_abstract_orders_words():
    inv = {"Deep": [0], "learning": [1], "works": [2]}
    assert openalex._reconstruct_abstract(inv) == "Deep learning works"
    assert openalex._reconstruct_abstract(None) == ""


# --- dedup --------------------------------------------------------------------

def test_dedup_by_doi():
    papers = [_paper("Title A", doi="10.1/x"), _paper("Different title", doi="10.1/X")]
    kept, removed = sources._dedup(papers)
    assert removed == 1 and len(kept) == 1


def test_dedup_by_title_when_no_doi():
    papers = [_paper("Same Title", source="Semantic Scholar"), _paper("same   title", source="OpenAlex")]
    kept, removed = sources._dedup(papers)
    assert removed == 1 and len(kept) == 1


def test_dedup_keeps_distinct_papers():
    papers = [_paper("Alpha", doi="10.1/a"), _paper("Beta", doi="10.1/b")]
    kept, removed = sources._dedup(papers)
    assert removed == 0 and len(kept) == 2


def test_interleave_round_robins():
    a = [_paper("a1"), _paper("a2")]
    b = [_paper("b1")]
    titles = [p["title"] for p in sources._interleave([a, b])]
    assert titles == ["a1", "b1", "a2"]


# --- merge provenance ---------------------------------------------------------

def test_merge_counts_and_dedup():
    s2 = SearchResult(
        papers=[_paper("Shared", doi="10.1/s", source="Semantic Scholar"), _paper("S2 only", doi="10.1/2", source="Semantic Scholar")],
        total_matches=100, fetched=5, excluded_no_abstract=1, excluded_by_filter=0,
        sources={"Semantic Scholar": 2}, databases=["Semantic Scholar"],
    )
    oa = SearchResult(
        papers=[_paper("Shared", doi="10.1/s", source="OpenAlex"), _paper("OA only", doi="10.1/o", source="OpenAlex")],
        total_matches=200, fetched=4, excluded_no_abstract=2, excluded_by_filter=1,
        sources={"OpenAlex": 2}, databases=["OpenAlex"],
    )
    merged = sources._merge([s2, oa], sort="relevance", limit=20, failed=[])
    assert merged.total_matches == 300            # identified across both databases
    assert merged.fetched == 9
    assert merged.excluded_no_abstract == 3
    assert merged.excluded_by_filter == 1
    assert merged.excluded_duplicates == 1        # "Shared" removed once
    assert len(merged.papers) == 3
    assert merged.databases == ["Semantic Scholar", "OpenAlex"]
    assert sum(merged.sources.values()) == 3


def test_merge_citations_sort_orders_desc():
    s2 = SearchResult(papers=[_paper("low", doi="10.1/l", citation_count=3)], databases=["Semantic Scholar"])
    oa = SearchResult(papers=[_paper("high", doi="10.1/h", citation_count=99)], databases=["OpenAlex"])
    merged = sources._merge([s2, oa], sort="citations", limit=20, failed=[])
    assert [p["title"] for p in merged.papers] == ["high", "low"]


def test_dual_query_searches_each_query_and_dedups_databases():
    calls = []

    def rec(q, **k):
        calls.append(q)
        return SearchResult(
            papers=[_paper(f"P-{q}", doi=f"10.1/{q}")],
            sources={"Rec": 1},
            databases=["Rec"],
        )

    original = dict(sources._SOURCES)
    sources._SOURCES.clear()
    sources._SOURCES.update({"rec": (rec, "Rec")})
    try:
        res = sources.search(["alpha", "beta"], databases=("rec",))
        assert calls == ["alpha", "beta"]  # both queries issued
        assert len(res.papers) == 2  # distinct papers merged
        assert res.databases == ["Rec"]  # same source listed once, not per-query
    finally:
        sources._SOURCES.clear()
        sources._SOURCES.update(original)


def test_search_degrades_when_one_source_fails():
    good = SearchResult(papers=[_paper("A", doi="10.1/a")], total_matches=1, fetched=1,
                        sources={"Good": 1}, databases=["Good"])

    def ok(*a, **k):
        return good

    def boom(*a, **k):
        raise RuntimeError("source down")

    original = dict(sources._SOURCES)
    sources._SOURCES.clear()
    sources._SOURCES.update({"good": (ok, "Good"), "bad": (boom, "Bad")})
    try:
        res = sources.search("x", databases=("good", "bad"))
        assert res.failed_databases == ["Bad"]
        assert len(res.papers) == 1
        # And if everything fails, it raises rather than returning empty.
        sources._SOURCES["good"] = (boom, "Good")
        raised = False
        try:
            sources.search("x", databases=("good", "bad"))
        except sources.SearchError:
            raised = True
        assert raised
    finally:
        sources._SOURCES.clear()
        sources._SOURCES.update(original)


# --- verify gate --------------------------------------------------------------

_MATRIX = """## 文獻矩陣

| 標題 | 作者 | 年份 | 引用數 | 研究方法 | 主要發現 |
| --- | --- | --- | --- | --- | --- |
{rows}

## 研究趨勢

### 1. 點

內文。
"""


def _analysis(rows):
    body = "\n".join(f"| {r} | Lin | 2020 | 5 | 實驗 | 結果 |" for r in rows)
    return _MATRIX.format(rows=body)


def test_verify_all_rows_matched():
    papers = [_paper("Deep Learning for X"), _paper("A Survey of Y: Methods")]
    # second row is a truncation of the real title -> should still match (substring)
    result = verify_matrix(_analysis(["Deep Learning for X", "A Survey of Y"]), papers)
    assert result.checked
    assert result.matched_rows == 2
    assert result.unmatched_titles == []
    assert result.ok


def test_verify_flags_fabricated_row():
    papers = [_paper("Deep Learning for X")]
    result = verify_matrix(_analysis(["Deep Learning for X", "Totally Invented Paper"]), papers)
    assert result.matched_rows == 1
    assert result.unmatched_titles == ["Totally Invented Paper"]
    assert not result.ok


def test_verify_reports_missing_papers():
    papers = [_paper("Used Paper"), _paper("Ignored Paper")]
    result = verify_matrix(_analysis(["Used Paper"]), papers)
    assert "Ignored Paper" in result.missing_papers


def test_verify_no_table_marks_unchecked():
    result = verify_matrix("## 研究趨勢\n\n沒有表格。", [_paper("X")])
    assert result.checked is False
    assert result.ok is False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
