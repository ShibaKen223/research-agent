"""Offline unit tests for the Haiku relevance gate.

No network: anthropic.Anthropic is monkeypatched with a fake client returning
canned scores, so these test the parsing, the keep/drop split, and the fail-open
fallbacks. Runs under pytest or as a plain script.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import cache, relevance  # noqa: E402

# Don't touch the on-disk cache during tests.
cache.disable()


class _FakeClient:
    def __init__(self, text):
        self.messages = SimpleNamespace(
            create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
        )


def _with_fake_client(text, fn):
    original = relevance.anthropic.Anthropic
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    relevance.anthropic.Anthropic = lambda api_key: _FakeClient(text)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        return fn()
    finally:
        relevance.anthropic.Anthropic = original
        if original_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = original_key


def _papers(n):
    return [{"title": f"Paper {i}", "abstract": f"abstract {i}"} for i in range(n)]


# --- score parsing ------------------------------------------------------------

def test_parse_scores_plain_json():
    assert relevance._parse_scores('{"0": 3, "1": 0}', 2) == {0: 3, 1: 0}


def test_parse_scores_tolerates_code_fence_and_prose():
    text = "Here are the scores:\n```json\n{\"0\": 2, \"1\": 1}\n```"
    assert relevance._parse_scores(text, 2) == {0: 2, 1: 1}


def test_parse_scores_drops_out_of_range_indices():
    assert relevance._parse_scores('{"0": 3, "5": 3}', 2) == {0: 3}


def test_parse_scores_returns_none_on_garbage():
    assert relevance._parse_scores("not json at all", 2) is None


def test_coerce_int_keys_handles_json_string_keys():
    # Cache round-trip turns {0:3} into {"0":3}; must come back as int keys.
    assert relevance._coerce_int_keys({"0": 3, "1": 0}) == {0: 3, 1: 0}
    assert relevance._coerce_int_keys({"bad": "x"}) is None
    assert relevance._coerce_int_keys("not a dict") is None


def test_cached_string_keyed_scores_still_split_correctly():
    # Regression: a cache hit returns JSON string keys; the gate must still drop
    # the off-topic paper, not keep everything (the cache-path bug).
    papers = _papers(2)
    original_get = relevance.cache.get
    relevance.cache.get = lambda ns, k: {"0": 3, "1": 0}  # JSON-style string keys
    try:
        result = relevance.filter_by_relevance("topic", papers)
    finally:
        relevance.cache.get = original_get
    assert result.checked
    assert result.kept == [papers[0]]
    assert result.dropped == [papers[1]]


# --- keep/drop split ----------------------------------------------------------

def test_filter_keeps_relevant_drops_offtopic():
    papers = _papers(2)
    result = _with_fake_client(
        '{"0": 3, "1": 0}', lambda: relevance.filter_by_relevance("topic", papers)
    )
    assert result.checked
    assert result.kept == [papers[0]]
    assert result.dropped == [papers[1]]
    assert not result.inconclusive


def test_filter_missing_score_defaults_to_keep():
    papers = _papers(2)
    # Only paper 0 scored; paper 1 omitted -> kept (benefit of the doubt).
    result = _with_fake_client('{"0": 3}', lambda: relevance.filter_by_relevance("t", papers))
    assert result.kept == papers
    assert result.dropped == []


def test_filter_all_offtopic_keeps_all_but_flags_inconclusive():
    papers = _papers(2)
    result = _with_fake_client(
        '{"0": 0, "1": 0}', lambda: relevance.filter_by_relevance("t", papers)
    )
    assert result.checked
    assert result.inconclusive
    assert result.kept == papers  # never empties the run
    assert result.dropped == []


# --- fail-open fallbacks ------------------------------------------------------

def test_filter_unparseable_reply_keeps_all_unchecked():
    papers = _papers(3)
    result = _with_fake_client("???", lambda: relevance.filter_by_relevance("t", papers))
    assert result.checked is False
    assert result.kept == papers


def test_filter_without_api_key_keeps_all_unchecked():
    original_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        papers = _papers(2)
        result = relevance.filter_by_relevance("t", papers)
        assert result.checked is False
        assert result.kept == papers
    finally:
        if original_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_key


def test_filter_empty_papers_is_noop():
    result = relevance.filter_by_relevance("t", [])
    assert result.checked is False
    assert result.kept == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
