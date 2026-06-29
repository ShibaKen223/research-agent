"""Offline unit tests for report assembly (no API, no network).

Focus: the report must carry exactly ONE references section — the program-built
one — even when the model emits its own (which would otherwise duplicate it and
reintroduce hallucinated/transcribed DOIs).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import report  # noqa: E402
from research_agent.ndltd import ThesisCrossCheckResult  # noqa: E402
from research_agent.semantic_scholar import SearchResult  # noqa: E402

_FOUR_SECTIONS = """## 文獻矩陣

| 標題 | 作者 | 年份 | 期刊/會議 | 引用數 | 研究方法 | 主要發現 |
| --- | --- | --- | --- | --- | --- | --- |
| Real Paper | Lin | 2021 | Venue | 1 | 實驗 | 結果 |

## 研究趨勢

### 1. 點

內文。

## 研究缺口

### 1. 點

內文。

## 碩論題目建議

### 題目一

**題目**

> 價值
"""


# --- the stripper ------------------------------------------------------------

def test_strip_removes_trailing_chinese_references():
    md = _FOUR_SECTIONS + "\n## 參考文獻\n\n1. 模型抄的 DOI 10.9/wrong\n"
    out = report._strip_model_references(md)
    assert "參考文獻" not in out
    assert "10.9/wrong" not in out
    assert "## 碩論題目建議" in out  # earlier sections survive


def test_strip_removes_english_references_midbody_keeps_following():
    md = "## A\n\nbody\n\n## References\n\n1. foo\n\n## B\n\nkeep me\n"
    out = report._strip_model_references(md)
    assert "References" not in out
    assert "foo" not in out
    assert "## B" in out and "keep me" in out


def test_strip_leaves_text_without_references_untouched():
    out = report._strip_model_references(_FOUR_SECTIONS)
    assert out.strip() == _FOUR_SECTIONS.strip()


# --- build_report integration ------------------------------------------------

def test_build_report_has_exactly_one_references_section():
    papers = [{
        "title": "Real Paper", "authors": ["Alice Lin"], "year": 2021,
        "venue": "Venue", "doi": "10.1/real", "url": "https://x/real",
    }]
    # The model wrongly appended its own 參考文獻 with a transcribed (wrong) DOI.
    analysis = _FOUR_SECTIONS + "\n## 參考文獻\n\n1. Lin (2021). Real Paper. 10.9/WRONG\n"
    stats = SearchResult(papers=papers, sources={"OpenAlex": 1}, databases=["OpenAlex"])

    out = report.build_report(
        "kw", 1, analysis, queries=["kw"], stats=stats, papers=papers,
    )
    assert out.count("## 參考文獻") == 1
    assert "10.9/WRONG" not in out  # the model's transcribed DOI is gone
    assert "https://doi.org/10.1/real" in out  # the authoritative one remains


# --- honesty annotations -----------------------------------------------------

def test_unverified_sections_get_caveat_verified_ones_dont():
    out = report.build_report("kw", 17, _FOUR_SECTIONS)
    # Exactly the two inference-only sections are flagged, with the sample size.
    assert out.count("未經程式驗證") == 2
    assert "17 篇摘要上的歸納推論" in out
    # The caveat sits under 研究缺口/碩論題目建議, not under 文獻矩陣/研究趨勢.
    matrix_to_trend = out[out.index("## 文獻矩陣") : out.index("## 研究趨勢")]
    assert "未經程式驗證" not in matrix_to_trend


def test_search_appendix_discloses_chinese_coverage_gap():
    stats = SearchResult(papers=[], sources={"OpenAlex": 1}, databases=["OpenAlex"])
    out = report.build_report("kw", 1, _FOUR_SECTIONS, queries=["kw"], stats=stats)
    assert "未涵蓋華藝" in out and "臺灣碩博士論文網" in out


# --- 臺灣碩博士論文對照 (ndltd) section ---------------------------------------

def test_thesis_section_lists_scored_theses_with_metadata():
    res = ThesisCrossCheckResult(
        checked=True, scored=True, matched=3, years=[113, 112],
        theses=[{
            "title": "深度學習於醫療影像", "title_en": "Deep Learning for Imaging",
            "school": "臺灣大學", "dept": "資工系", "year": "113", "degree": "碩士",
            "author": "王小明", "advisor": "李大華",
            "url": "https://hdl.handle.net/11296/abc",
        }],
    )
    out = report._thesis_section(res)
    assert "## 臺灣碩博士論文對照" in out
    # The honest, un-missable limits: title-only + recent years + Haiku scoring.
    assert "僅依標題" in out and "Haiku" in out
    assert "113、112" in out  # academic years searched
    assert "標題命中：3" in out  # scored path reports the matched count
    # The thesis itself, with its real metadata fields rendered.
    assert "深度學習於醫療影像" in out and "Deep Learning for Imaging" in out
    assert "臺灣大學·資工系" in out and "113 學年度 碩士" in out
    assert "王小明" in out and "指導：李大華" in out
    assert "https://hdl.handle.net/11296/abc" in out


def test_thesis_section_unscored_warns():
    res = ThesisCrossCheckResult(
        checked=True, scored=False, matched=5, years=[113],
        theses=[{"title": "某論文", "year": "113"}],
    )
    out = report._thesis_section(res)
    assert "未能評分" in out  # degraded honestly: title hits shown, flagged unscored


def test_thesis_section_none_found_is_not_proof_of_novelty():
    res = ThesisCrossCheckResult(checked=True, scored=True, matched=0, years=[113], theses=[])
    out = report._thesis_section(res)
    assert "未找到" in out and "並非" in out  # absence != "no related research"


def test_thesis_section_download_failure_degrades():
    out = report._thesis_section(ThesisCrossCheckResult(checked=False))
    assert "下載失敗" in out and "不影響其他章節" in out


def test_build_report_includes_thesis_section_only_when_given():
    res = ThesisCrossCheckResult(checked=True, scored=True, matched=1, years=[113],
                                 theses=[{"title": "某碩論", "year": "113"}])
    with_ndltd = report.build_report("kw", 1, _FOUR_SECTIONS, ndltd=res)
    assert "## 臺灣碩博士論文對照" in with_ndltd and "某碩論" in with_ndltd
    # Omitting the param (the default) must not inject the section.
    assert "## 臺灣碩博士論文對照" not in report.build_report("kw", 1, _FOUR_SECTIONS)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
