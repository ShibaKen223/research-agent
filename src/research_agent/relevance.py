"""Topical relevance gate: drop off-topic papers before the expensive analysis.

A keyword search returns whatever merely *mentions* the words — a search for
「大型語言模型 就業市場」 happily pulls in papers on ammunition-depot siting or
group learning in a Japanese course that just happen to contain those characters.
`verify.py` later proves the matrix's papers are *real*, but it can't tell that
they are *off-topic*; the model then writes a confident, well-written review of a
near-random sample. That false rigor is the single biggest threat to this tool's
credibility.

This module is the fix: one cheap Haiku call scores every retrieved paper for how
directly it matches the user's actual topic, and the clearly-irrelevant ones are
dropped before they reach the Sonnet analysis (which also stops paying to analyse
junk). The dropped count and titles are disclosed in the report's 檢索說明 appendix.

It is deliberately fail-open: any error, unparseable reply, or a verdict that
would discard *every* paper falls back to keeping all of them (flagged
`inconclusive`), so the gate can never empty a run or abort it — at worst it does
nothing and says so.
"""

import json
import os
from dataclasses import dataclass, field

import anthropic

from research_agent import cache

# Cheap model on purpose: scoring titles/abstracts is easy and the user's API
# budget is limited, so we never spend Sonnet-level tokens on the gate.
RELEVANCE_MODEL = "claude-haiku-4-5-20251001"

# Scores are 0-3 (0 = unrelated … 3 = directly on-topic). Keep >= this.
KEEP_THRESHOLD = 2
# Abstracts are truncated in the prompt: the first chunk is plenty to judge
# topicality and keeps the (per-paper) token cost negligible.
_ABSTRACT_CHARS = 320
MAX_TOKENS = 1024


@dataclass
class RelevanceResult:
    checked: bool = True  # False when the gate didn't run (no key / error / disabled)
    kept: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)  # papers judged off-topic
    inconclusive: bool = False  # gate ran but kept everything as a safety fallback
    model: str = RELEVANCE_MODEL

    @property
    def dropped_titles(self) -> list[str]:
        return [p.get("title", "") for p in self.dropped]


_PROMPT = """\
You are screening search results for a literature review on this topic:

「{keyword}」

Below is a numbered list of papers (title + abstract excerpt). For each paper, \
rate how directly it is about THIS topic, on a 0-3 scale:
- 3 = squarely on-topic (a core paper for this topic)
- 2 = clearly related (same subject area, useful for the review)
- 1 = only tangential (merely mentions the words; different real subject)
- 0 = unrelated (a keyword coincidence)

Judge the paper's actual subject, not whether it shares a few words. Output ONLY \
a JSON object mapping each paper's number (as a string) to its integer score, e.g. \
{{"0": 3, "1": 0}}. No explanation, no code fence.

{papers_block}
"""


def filter_by_relevance(
    keyword: str, papers: list[dict], model: str = RELEVANCE_MODEL
) -> RelevanceResult:
    """Score `papers` for topical relevance to `keyword` and split kept/dropped.

    Returns a `RelevanceResult`. On a missing API key, an API/parse error, or a
    verdict that would drop everything, it keeps all papers (`inconclusive=True`,
    or `checked=False` if it never reached the model) rather than risk emptying
    the run. A single Haiku call scores the whole batch."""
    if not papers:
        return RelevanceResult(checked=False, kept=[], model=model)

    block = _papers_block(papers)
    prompt = _PROMPT.format(keyword=keyword, papers_block=block)

    ck = cache.key("relevance", model, prompt)
    cached_scores = cache.get("relevance", ck)
    if cached_scores is not None:
        return _split(papers, cached_scores, model)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Don't raise: the gate is an enhancement, not a hard dependency.
        return RelevanceResult(checked=False, kept=list(papers), model=model)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        scores = _parse_scores(text, len(papers))
    except Exception:  # noqa: BLE001 — any failure falls back to keeping everything
        return RelevanceResult(checked=False, kept=list(papers), model=model)

    if scores is None:
        return RelevanceResult(checked=False, kept=list(papers), model=model)

    cache.set("relevance", ck, scores)
    return _split(papers, scores, model)


def _split(papers: list[dict], scores: dict[int, int], model: str) -> RelevanceResult:
    """Partition papers by score. Missing scores default to 'keep' (benefit of the
    doubt). If the verdict would drop everything, keep all and flag inconclusive."""
    kept, dropped = [], []
    for i, paper in enumerate(papers):
        if scores.get(i, KEEP_THRESHOLD) >= KEEP_THRESHOLD:
            kept.append(paper)
        else:
            dropped.append(paper)

    if not kept:
        # The whole batch scored low. That's real signal, but emptying the run
        # breaks everything downstream, so keep all and let the report flag it.
        return RelevanceResult(
            checked=True, kept=list(papers), dropped=[], inconclusive=True, model=model
        )
    return RelevanceResult(checked=True, kept=kept, dropped=dropped, model=model)


def _papers_block(papers: list[dict]) -> str:
    lines = []
    for i, p in enumerate(papers):
        title = (p.get("title") or "").strip()
        abstract = (p.get("abstract") or "").strip().replace("\n", " ")
        if len(abstract) > _ABSTRACT_CHARS:
            abstract = abstract[:_ABSTRACT_CHARS] + "…"
        lines.append(f"[{i}] {title}\n{abstract}")
    return "\n\n".join(lines)


def _parse_scores(text: str, n: int) -> dict[int, int] | None:
    """Pull the {index: score} JSON out of the model reply, tolerating a stray
    code fence or surrounding prose. Returns None if nothing usable is found."""
    if not text:
        return None
    blob = text
    if "{" in blob and "}" in blob:
        blob = blob[blob.index("{") : blob.rindex("}") + 1]
    try:
        raw = json.loads(blob)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    scores: dict[int, int] = {}
    for k, v in raw.items():
        try:
            idx = int(str(k).strip())
            score = int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < n:
            scores[idx] = score
    return scores or None
