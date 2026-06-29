"""Offline tests for the opt-in claim-support check (no network).

anthropic.Anthropic is monkeypatched with a fake client returning canned scores;
these cover pairing matrix rows to their abstracts, the supported/unsupported
split, the cache-string-key path (the bug that bit relevance.py), and the
fail-open fallbacks. Runs under pytest or as a plain script.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import cache, claim_check  # noqa: E402

cache.disable()  # never touch the on-disk cache during tests


class _FakeClient:
    def __init__(self, text):
        self.messages = SimpleNamespace(
            create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
        )


def _with_fake_client(text, fn):
    original = claim_check.anthropic.Anthropic
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    claim_check.anthropic.Anthropic = lambda api_key: _FakeClient(text)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        return fn()
    finally:
        claim_check.anthropic.Anthropic = original
        if original_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = original_key


_PAPERS = [
    {"title": "Paper A", "abstract": "We show that X increases Y by 10%."},
    {"title": "Paper B", "abstract": "A qualitative study of teachers."},
]


def _matrix(rows: str) -> str:
    return (
        "## 文獻矩陣\n\n"
        "| 標題 | 作者 | 年份 | 期刊/會議 | 引用數 | 研究方法 | 主要發現 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n" + rows + "\n"
    )


_ANALYSIS = _matrix(
    "| Paper A | A | 2020 | V | 1 | 量化 | X 使 Y 增加一成 |\n"
    "| Paper B | B | 2021 | V | 2 | 質性 | 教師的質性研究 |"
)


# --- pairing matrix rows to abstracts ----------------------------------------

def test_pairs_matches_findings_to_abstracts():
    pairs = claim_check._pairs(_ANALYSIS, _PAPERS)
    assert len(pairs) == 2
    assert pairs[0][0] == "Paper A"
    assert pairs[0][1] == "X 使 Y 增加一成"
    assert "increases Y" in pairs[0][2]


def test_pairs_skips_unmatched_rows():
    md = _matrix("| Ghost Paper | G | 2020 | V | 0 | 量化 | 杜撰發現 |")
    assert claim_check._pairs(md, _PAPERS) == []


def test_pairs_skips_rows_without_abstract():
    papers = [{"title": "Paper A", "abstract": ""}]
    md = _matrix("| Paper A | A | 2020 | V | 1 | 量化 | 某發現 |")
    assert claim_check._pairs(md, papers) == []


# --- supported / unsupported split -------------------------------------------

def test_flags_unsupported_finding():
    result = _with_fake_client(
        '{"0": 2, "1": 0}', lambda: claim_check.check_claims(_ANALYSIS, _PAPERS)
    )
    assert result.checked
    assert result.total == 2
    assert result.supported == 1
    assert [i.title for i in result.unsupported] == ["Paper B"]


def test_partial_support_is_not_flagged():
    result = _with_fake_client(
        '{"0": 1, "1": 1}', lambda: claim_check.check_claims(_ANALYSIS, _PAPERS)
    )
    assert result.supported == 2
    assert result.unsupported == []


def test_missing_score_defaults_to_supported():
    result = _with_fake_client('{"0": 2}', lambda: claim_check.check_claims(_ANALYSIS, _PAPERS))
    assert result.supported == 2
    assert result.unsupported == []


def test_cached_string_keys_still_split():
    # Regression twin of relevance's cache bug: JSON string keys must be coerced.
    original_get = claim_check.cache.get
    claim_check.cache.get = lambda ns, k: {"0": 2, "1": 0}
    try:
        result = claim_check.check_claims(_ANALYSIS, _PAPERS)
    finally:
        claim_check.cache.get = original_get
    assert result.checked
    assert [i.title for i in result.unsupported] == ["Paper B"]


# --- fail-open ---------------------------------------------------------------

def test_no_pairs_is_unchecked():
    md = _matrix("| Ghost | G | 2020 | V | 0 | 量化 | 杜撰 |")
    assert claim_check.check_claims(md, _PAPERS).checked is False


def test_no_table_is_unchecked():
    assert claim_check.check_claims("## 文獻矩陣\n\n（沒有表格）\n", _PAPERS).checked is False


def test_unparseable_reply_is_unchecked():
    result = _with_fake_client("???", lambda: claim_check.check_claims(_ANALYSIS, _PAPERS))
    assert result.checked is False


def test_without_api_key_is_unchecked():
    original_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert claim_check.check_claims(_ANALYSIS, _PAPERS).checked is False
    finally:
        if original_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_key


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
