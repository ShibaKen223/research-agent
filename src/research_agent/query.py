"""Optionally translate a (often Chinese) research keyword into an English search
query before hitting Semantic Scholar, whose corpus is overwhelmingly English.

This is opt-in (CLI `--translate`, web toggle) and deliberately cheap: it uses a
small model (Haiku) with a tiny token budget, and skips the API call entirely
when the keyword is already plain ASCII (so an English keyword costs nothing).

Also provides `suggest_keywords()`, used to propose broader/alternative search
terms when a search comes back sparse — gated behind a result-count threshold
by callers so it only fires on the searches that actually need it.
"""

import os

import anthropic

# Cheap model on purpose — translation is a trivial task and the user's API
# budget is limited, so we never spend Sonnet-level tokens on it.
TRANSLATE_MODEL = "claude-haiku-4-5-20251001"

# Below this many papers, a search is "sparse" enough to be worth one extra
# Haiku call suggesting broader/alternative keywords.
SPARSE_RESULT_THRESHOLD = 5

_PROMPT = """\
Convert the following research topic into a concise English search query for an \
academic paper database (Semantic Scholar). Output ONLY the query terms in \
English on a single line — no quotation marks, no explanation, no labels. If the \
topic is already in English, return it unchanged.

Research topic: {keyword}
"""


def needs_translation(keyword: str) -> bool:
    """A non-ASCII keyword (e.g. Chinese) is worth translating; a plain-ASCII one
    is assumed already English, so we can skip the API call and spend nothing."""
    return not keyword.isascii()


def translate_to_english_query(keyword: str, model: str = TRANSLATE_MODEL) -> str:
    """Return an English search query for `keyword`.

    Skips the API call (returns `keyword` unchanged) when it already looks
    English. Raises RuntimeError if the API key is missing; lets anthropic API
    errors propagate so callers can decide whether to fall back to the original.
    """
    if not needs_translation(keyword):
        return keyword

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Put it in a .env file or export it as an env var."
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=64,  # a search query is short; cap output to keep cost negligible
        temperature=0,
        messages=[{"role": "user", "content": _PROMPT.format(keyword=keyword)}],
    )
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    # Be defensive: keep only the first line and strip stray quotes the model may add.
    first_line = text.splitlines()[0].strip().strip("\"'").strip() if text else ""
    return first_line or keyword


_SUGGEST_PROMPT = """\
A search for the following research topic on an academic paper database (Semantic \
Scholar) returned very few results. Suggest {count} alternative English search \
queries more likely to find related papers — broaden overly specific qualifiers, \
use synonyms, or use a more general term for the same topic. Output ONLY the \
queries, one per line, no numbering, no quotation marks, no explanation.

Research topic: {keyword}
"""


def suggest_keywords(keyword: str, count: int = 3, model: str = TRANSLATE_MODEL) -> list[str]:
    """Ask Haiku for `count` alternative/broader search queries for `keyword`.

    Only meant to be called when a search already came back sparse — callers
    should gate this behind a result-count threshold so it doesn't fire on
    every search. Raises RuntimeError if the API key is missing; lets
    anthropic API errors propagate so callers can decide whether to swallow them.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Put it in a .env file or export it as an env var."
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=128,  # a handful of short queries; cap output to keep cost negligible
        temperature=0,
        messages=[{"role": "user", "content": _SUGGEST_PROMPT.format(keyword=keyword, count=count)}],
    )
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    lines = [line.strip().strip("\"'-•").strip() for line in text.splitlines()]
    return [line for line in lines if line][:count]
