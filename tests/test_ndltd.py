"""Offline unit tests for ndltd.py (no network, no API).

Covers the pure CSV-parsing + title-matching helpers against the real open-data
column layout. Download + Haiku scoring (`search_theses`) is integration-only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import ndltd  # noqa: E402

_HEADER = "論文名稱(中文),論文名稱(外文),學校名稱,系所名稱,畢業學年度,學位類別,作者,指導教授,博碩士論文網址"
# Leading ﻿ mimics the UTF-8 BOM the real files carry.
_CSV = (
    "﻿" + _HEADER + "\n"
    "深度學習於醫療影像之應用,Deep Learning for Medical Imaging,臺灣大學,資訊工程學系,113,碩士,王小明,李大華,https://hdl.handle.net/11296/abc\n"
    "區塊鏈與供應鏈,Blockchain and Supply Chain,清華大學,資訊管理研究所,112,博士,陳美麗,張三,https://hdl.handle.net/11296/def\n"
)


def test_header_index_maps_chinese_columns():
    idx = ndltd._header_index(_HEADER.split(","))
    assert idx == {
        "title": 0, "title_en": 1, "school": 2, "dept": 3, "year": 4,
        "degree": 5, "author": 6, "advisor": 7, "url": 8,
    }


def test_header_index_handles_bom_on_first_column():
    idx = ndltd._header_index(("﻿論文名稱(中文)", "學校名稱"))
    assert idx["title"] == 0 and idx["school"] == 1


def test_iter_theses_parses_with_bom():
    rows = list(ndltd._iter_theses(_CSV))
    assert len(rows) == 2
    r = rows[0]
    assert r["title"] == "深度學習於醫療影像之應用"
    assert r["title_en"] == "Deep Learning for Medical Imaging"
    assert r["school"] == "臺灣大學" and r["year"] == "113" and r["degree"] == "碩士"
    assert r["author"] == "王小明" and r["advisor"] == "李大華"
    assert r["url"].startswith("https://hdl.handle.net/")


def test_iter_theses_empty_when_no_title_column():
    assert list(ndltd._iter_theses("foo,bar\n1,2\n")) == []


def test_terms_filters_short_and_lowercases():
    assert ndltd._terms("AI 教育") == ["ai", "教育"]
    assert ndltd._terms("  深度學習  ") == ["深度學習"]
    assert ndltd._terms("a 我") == []  # single-char terms dropped


def test_match_score_counts_distinct_terms():
    rows = list(ndltd._iter_theses(_CSV))
    # "深度學習" hits the Chinese title, "medical" hits the English title => 2.
    assert ndltd._match_score(rows[0], ["深度學習", "medical"]) == 2
    assert ndltd._match_score(rows[0], ["區塊鏈"]) == 0


def test_year_int():
    assert ndltd._year_int({"year": "113"}) == 113
    assert ndltd._year_int({"year": ""}) == 0
    assert ndltd._year_int({}) == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
