"""Offline unit tests for report assembly (no API, no network).

Focus: the report must carry exactly ONE references section — the program-built
one — even when the model emits its own (which would otherwise duplicate it and
reintroduce hallucinated/transcribed DOIs).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import report  # noqa: E402
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
