"""Offline unit tests for the arXiv source (Atom feed parsing + filtering).

No network: `_parse_feed` is exercised on a hand-built feed, and `search_papers`
is tested either via its no-network early-return (min_citations) or by stubbing
`_get`. Runs under pytest or as a plain script.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import arxiv, cache  # noqa: E402

cache.disable()

_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2301.12345v2</id>
    <published>2023-01-30T18:00:00Z</published>
    <title>Deep Learning for
      Widgets</title>
    <summary>  We study widgets
      with deep nets.  </summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
    <arxiv:doi>10.1234/XYZ.2023</arxiv:doi>
    <arxiv:journal_ref>Journal of Widgets 12 (2023) 1-10</arxiv:journal_ref>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1900.00001v1</id>
    <published>1999-05-01T00:00:00Z</published>
    <title>An Old Preprint</title>
    <summary>Old work.</summary>
    <author><name>Alice Roe</name></author>
  </entry>
</feed>
"""


def test_parse_feed_reads_total_and_entries():
    papers, total = arxiv._parse_feed(_FEED)
    assert total == 2
    assert len(papers) == 2


def test_normalize_published_paper():
    papers, _ = arxiv._parse_feed(_FEED)
    p = papers[0]
    # Whitespace inside the title/abstract is collapsed.
    assert p["title"] == "Deep Learning for Widgets"
    assert p["abstract"] == "We study widgets with deep nets."
    assert p["authors"] == ["Jane Doe", "John Smith"]
    assert p["year"] == 2023
    assert p["doi"] == "10.1234/xyz.2023"  # normalized (lower-cased)
    assert p["venue"] == "Journal of Widgets 12 (2023) 1-10"  # from journal_ref
    assert p["paper_id"] == "2301.12345v2"
    assert p["url"] == "http://arxiv.org/abs/2301.12345v2"
    assert p["citation_count"] == 0
    assert p["source"] == "arXiv"


def test_normalize_bare_preprint_defaults_venue_and_doi():
    papers, _ = arxiv._parse_feed(_FEED)
    p = papers[1]
    assert p["venue"] == "arXiv"  # no journal_ref -> the preprint server itself
    assert p["doi"] == ""  # no DOI element
    assert p["year"] == 1999


def test_parse_feed_raises_on_garbage():
    raised = False
    try:
        arxiv._parse_feed("not xml at all <<<")
    except arxiv.ArxivError:
        raised = True
    assert raised


def test_min_citations_skips_arxiv_without_network():
    # arXiv has no citation data, so any floor >= 1 returns empty (no HTTP call).
    res = arxiv.search_papers("anything", min_citations=1)
    assert res.papers == []
    assert res.databases == ["arXiv"]
    assert res.sources == {"arXiv": 0}


def test_search_papers_applies_year_filter():
    original = arxiv._get
    arxiv._get = lambda params: _FEED
    try:
        res = arxiv.search_papers("widgets", limit=20, year_from=2020)
    finally:
        arxiv._get = original
    titles = [p["title"] for p in res.papers]
    assert titles == ["Deep Learning for Widgets"]  # 1999 paper dropped
    assert res.fetched == 2
    assert res.excluded_by_filter == 1
    assert res.total_matches == 2
    assert res.sources == {"arXiv": 1}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
