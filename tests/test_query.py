"""Offline unit tests for query.py's Haiku-backed helpers.

No network and no Claude calls: anthropic.Anthropic is monkeypatched with a fake
client that returns canned text, so these test the prompt-response parsing only.
Runs under pytest (`pytest tests/`) or as a plain script
(`python tests/test_query.py`).
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import query  # noqa: E402


class _FakeClient:
    def __init__(self, text):
        self.messages = SimpleNamespace(
            create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])
        )


def _with_fake_client(text, fn):
    """Run `fn()` with anthropic.Anthropic replaced by a fake returning `text`,
    and a dummy API key set, restoring both afterwards."""
    original_anthropic = query.anthropic.Anthropic
    original_key = os.environ.get("ANTHROPIC_API_KEY")
    query.anthropic.Anthropic = lambda api_key: _FakeClient(text)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    try:
        return fn()
    finally:
        query.anthropic.Anthropic = original_anthropic
        if original_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = original_key


def test_suggest_academic_terms_parses_term_and_gloss():
    text = (
        "novice software engineer competency — 新手工程師能力框架\n"
        "early-career developer AI skills — 早期職涯開發者的 AI 技能\n"
    )
    terms = _with_fake_client(text, lambda: query.suggest_academic_terms("AI 初階工程師", count=5))
    assert terms[0] == query.AcademicTerm("novice software engineer competency", "新手工程師能力框架")
    assert terms[1] == query.AcademicTerm("early-career developer AI skills", "早期職涯開發者的 AI 技能")
    assert len(terms) == 2


def test_suggest_academic_terms_tolerates_missing_gloss():
    text = "deep learning\nreinforcement learning"
    terms = _with_fake_client(text, lambda: query.suggest_academic_terms("x", count=5))
    assert terms[0] == query.AcademicTerm("deep learning", "")
    assert terms[1] == query.AcademicTerm("reinforcement learning", "")


def test_suggest_academic_terms_strips_bullets_and_hyphen_separator():
    text = "- deep learning - 深度學習"
    terms = _with_fake_client(text, lambda: query.suggest_academic_terms("x", count=5))
    assert terms == [query.AcademicTerm("deep learning", "深度學習")]


def test_suggest_academic_terms_respects_count_cap():
    text = "\n".join(f"term{i} — gloss{i}" for i in range(10))
    terms = _with_fake_client(text, lambda: query.suggest_academic_terms("x", count=3))
    assert len(terms) == 3


def test_suggest_academic_terms_requires_api_key():
    original_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        raised = False
        try:
            query.suggest_academic_terms("x")
        except RuntimeError:
            raised = True
        assert raised
    finally:
        if original_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_key


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
