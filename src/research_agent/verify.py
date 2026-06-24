"""Programmatic faithfulness check for the generated 文獻矩陣.

`analyzer.PROMPT_TEMPLATE` forbids the model from inventing papers, but a prompt
is only a request. This module verifies it after the fact: every row of the
文獻矩陣 table must map to a paper that was actually sent to the model. Rows that
don't are surfaced as possible fabrications, turning the grounding rule from a
promise the model makes into a check the program enforces.

Matching is deliberately lenient (exact normalized title, substring, then a
difflib ratio) because the model may lightly reword or truncate a title; the aim
is to catch invented papers, not to punish cosmetic edits.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from research_agent.report_parser import parse_markdown_table, parse_report
from research_agent.text_utils import normalize_title

MATRIX_SECTION = "文獻矩陣"
TITLE_COLUMN = "標題"
_FUZZY_THRESHOLD = 0.85


@dataclass
class VerificationResult:
    checked: bool = True  # False when no 文獻矩陣 table could be parsed
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_titles: list[str] = field(default_factory=list)  # rows with no source paper
    missing_papers: list[str] = field(default_factory=list)  # papers absent from the matrix

    @property
    def ok(self) -> bool:
        return self.checked and not self.unmatched_titles


def verify_matrix(analysis_markdown: str, papers: list[dict]) -> VerificationResult:
    """Check the 文獻矩陣 in `analysis_markdown` against the `papers` actually
    retrieved. Returns a `VerificationResult`; `checked=False` if there was no
    parseable table (e.g. the model emitted a different layout)."""
    _, sections = parse_report(analysis_markdown)
    rows = parse_markdown_table(sections.get(MATRIX_SECTION, ""))
    if not rows:
        return VerificationResult(checked=False)

    paper_keys = [normalize_title(p.get("title")) for p in papers]  # aligned to `papers`
    matched_paper_idx: set[int] = set()
    matched = 0
    unmatched: list[str] = []

    for row in rows:
        raw_title = row.get(TITLE_COLUMN) or _first_value(row)
        idx = _best_match(normalize_title(raw_title), paper_keys)
        if idx is None:
            unmatched.append((raw_title or "(空白列)").strip())
        else:
            matched += 1
            matched_paper_idx.add(idx)

    missing = [
        papers[i].get("title", "") for i in range(len(papers)) if i not in matched_paper_idx
    ]
    return VerificationResult(
        checked=True,
        total_rows=len(rows),
        matched_rows=matched,
        unmatched_titles=unmatched,
        missing_papers=missing,
    )


def _best_match(key: str, paper_keys: list[str]) -> int | None:
    """Index of the best-matching paper for a matrix-row title key, or None."""
    if not key:
        return None
    best_idx: int | None = None
    best_score = 0.0
    for i, candidate in enumerate(paper_keys):
        if not candidate:
            continue
        if key == candidate or key in candidate or candidate in key:
            return i
        score = SequenceMatcher(None, key, candidate).ratio()
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx if best_score >= _FUZZY_THRESHOLD else None


def _first_value(row: dict[str, str]) -> str:
    for value in row.values():
        return value
    return ""
