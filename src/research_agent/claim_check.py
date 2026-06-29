"""Opt-in content check: is each 文獻矩陣 主要發現 actually supported by its abstract?

`verify.py` proves (for free) that every matrix row maps to a real, retrieved paper
and that the row's 作者/年份 match the metadata. But the model still *writes* the
主要發現 cell, and a fluent summary can quietly overstate — or invent — a result the
abstract never claims. That is the subtlest and most citation-damaging failure of
all, and the one neither the existence check nor the metadata checks can catch.

This is the deepest check: one Haiku batch call reads each matched row's claimed
finding against that paper's real abstract and scores whether the abstract supports
it. Rows the abstract doesn't support are surfaced in the 檢索說明 appendix.

It is **off by default** (`--verify-claims` to enable): unlike the metadata checks
it spends tokens on every run, and the user's API budget is tight. Like
`relevance.py` it is cached and fail-open — a missing key, API/parse error, or no
checkable rows degrades to "not checked" rather than guessing or aborting. (The
`_parse_scores`/`_coerce_int_keys` helpers mirror `relevance.py`'s, including the
cache-string-key fix; keep the two in sync if either changes.)
"""

import json
import os
from dataclasses import dataclass, field
from typing import NamedTuple

import anthropic

from research_agent import cache
from research_agent.report_parser import parse_markdown_table, parse_report
from research_agent.text_utils import normalize_title
from research_agent.verify import MATRIX_SECTION, TITLE_COLUMN, _best_match, _column

CLAIM_MODEL = "claude-haiku-4-5-20251001"
_FINDING_COLUMN = "主要發現"
# Support score: 0 = abstract doesn't support it, 1 = partial, 2 = clearly supported.
# Flag only 0, so a faithful paraphrase scored 1 is never accused.
_SUPPORTED_THRESHOLD = 1
_ABSTRACT_CHARS = 700
MAX_TOKENS = 1024


class ClaimIssue(NamedTuple):
    title: str  # the matrix row (matched paper)
    finding: str  # the claimed 主要發現 the abstract doesn't support


@dataclass
class ClaimCheckResult:
    checked: bool = True  # False when it didn't run (off / no key / no rows / error)
    total: int = 0  # rows actually checked (matched a paper, had a finding + abstract)
    supported: int = 0
    unsupported: list[ClaimIssue] = field(default_factory=list)
    model: str = CLAIM_MODEL


_PROMPT = """\
You are fact-checking a literature-review table against the source abstracts.

For each item you get a paper's ABSTRACT and a CLAIM (the review's stated "main \
finding" for that paper). Decide whether the abstract supports the claim:
- 2 = the abstract clearly states or directly implies the claim
- 1 = the abstract is partially or loosely consistent with the claim
- 0 = the abstract does NOT support the claim (it is absent from, or contradicted \
by, the abstract)

Judge ONLY against the given abstract text; do not use any outside knowledge. \
Output ONLY a JSON object mapping each item's number (as a string) to its integer \
score, e.g. {{"0": 2, "1": 0}}. No explanation, no code fence.

{items_block}
"""


def check_claims(
    analysis_markdown: str, papers: list[dict], model: str = CLAIM_MODEL
) -> ClaimCheckResult:
    """Check each 文獻矩陣 主要發現 against its paper's abstract. Returns a
    `ClaimCheckResult`; `checked=False` when there was nothing to check or the call
    couldn't run (missing key / error) — never raises, never alters the analysis."""
    pairs = _pairs(analysis_markdown, papers)
    if not pairs:
        return ClaimCheckResult(checked=False, model=model)

    prompt = _PROMPT.format(items_block=_items_block(pairs))

    ck = cache.key("claim_check", model, prompt)
    cached = cache.get("claim_check", ck)
    if cached is not None:
        scores = _coerce_int_keys(cached)
        if scores is not None:
            return _split(pairs, scores, model)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ClaimCheckResult(checked=False, model=model)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        scores = _parse_scores(text, len(pairs))
    except Exception:  # noqa: BLE001 — any failure degrades to "not checked"
        return ClaimCheckResult(checked=False, model=model)

    if scores is None:
        return ClaimCheckResult(checked=False, model=model)

    cache.set("claim_check", ck, scores)
    return _split(pairs, scores, model)


def _pairs(analysis_markdown: str, papers: list[dict]) -> list[tuple[str, str, str]]:
    """(title, finding, abstract) for every matrix row that maps to a retrieved
    paper, has a non-empty 主要發現, and whose paper has an abstract to check
    against. Unmatched rows are verify.py's concern, not this one."""
    _, sections = parse_report(analysis_markdown)
    rows = parse_markdown_table(sections.get(MATRIX_SECTION, ""))
    if not rows:
        return []
    paper_keys = [normalize_title(p.get("title")) for p in papers]
    pairs: list[tuple[str, str, str]] = []
    for row in rows:
        finding = _column(row, _FINDING_COLUMN)
        raw_title = (row.get(TITLE_COLUMN) or "").strip()
        if not finding or not raw_title:
            continue
        idx = _best_match(normalize_title(raw_title), paper_keys)
        if idx is None:
            continue
        abstract = (papers[idx].get("abstract") or "").strip()
        if not abstract:
            continue
        pairs.append((raw_title, finding, abstract))
    return pairs


def _split(
    pairs: list[tuple[str, str, str]], scores: dict[int, int], model: str
) -> ClaimCheckResult:
    """Partition checked rows into supported vs unsupported. A missing score
    defaults to supported (benefit of the doubt), matching the tool's
    don't-accuse-without-evidence bias."""
    supported = 0
    issues: list[ClaimIssue] = []
    for i, (title, finding, _abstract) in enumerate(pairs):
        if scores.get(i, _SUPPORTED_THRESHOLD) >= _SUPPORTED_THRESHOLD:
            supported += 1
        else:
            issues.append(ClaimIssue(title, finding))
    return ClaimCheckResult(
        checked=True, total=len(pairs), supported=supported, unsupported=issues, model=model
    )


def _items_block(pairs: list[tuple[str, str, str]]) -> str:
    out = []
    for i, (_title, finding, abstract) in enumerate(pairs):
        ab = abstract.replace("\n", " ")
        if len(ab) > _ABSTRACT_CHARS:
            ab = ab[:_ABSTRACT_CHARS] + "…"
        out.append(f"[{i}] CLAIM: {finding}\nABSTRACT: {ab}")
    return "\n\n".join(out)


# --- score parsing (twin of relevance.py's; keep in sync) ---------------------

def _coerce_int_keys(scores) -> dict[int, int] | None:
    """Normalize a cached scores dict (JSON round-trip makes keys strings) back to
    int keys. Returns None if nothing usable, so the caller recomputes."""
    if not isinstance(scores, dict):
        return None
    out: dict[int, int] = {}
    for k, v in scores.items():
        try:
            out[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out or None


def _parse_scores(text: str, n: int) -> dict[int, int] | None:
    """Pull the {index: score} JSON out of the reply, tolerating a stray code fence
    or surrounding prose. Returns None if nothing usable is found."""
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
