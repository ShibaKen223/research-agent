"""Programmatic faithfulness check for the generated 文獻矩陣.

`analyzer.PROMPT_TEMPLATE` forbids the model from inventing papers, but a prompt
is only a request. This module verifies it after the fact: every row of the
文獻矩陣 table must map to a paper that was actually sent to the model. Rows that
don't are surfaced as possible fabrications, turning the grounding rule from a
promise the model makes into a check the program enforces.

Matching is deliberately lenient (exact normalized title, substring, then a
difflib ratio) because the model may lightly reword or truncate a title; the aim
is to catch invented papers, not to punish cosmetic edits.

Beyond mere existence, once a row is matched to its real paper this also
cross-checks the **content** of two low-ambiguity columns against that paper's
actual metadata — for free, no API call:
- 作者：the row's author must share at least one name token with a real author of
  the matched paper. A row attributing the paper to someone who isn't on it
  (張冠李戴) is flagged. Deliberately conservative — only a *zero*-overlap of
  Latin name tokens trips it, so cosmetic differences ("Acemoglu" vs
  "Daron Acemoglu", listing the 2nd author) never false-positive.
- 年份：a four-digit year in the row that conflicts with the paper's real year is
  flagged (transcription drift).
Whether each row's free-text 主要發現 is actually supported by the abstract is a
semantic question this module can't answer for free; that is the separate,
opt-in, Haiku-backed `claim_check.py`.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import NamedTuple

from research_agent.report_parser import parse_markdown_table, parse_report
from research_agent.text_utils import normalize_title

MATRIX_SECTION = "文獻矩陣"
TITLE_COLUMN = "標題"
_AUTHOR_COLUMN = "作者"
_YEAR_COLUMN = "年"
_FUZZY_THRESHOLD = 0.85

# Tokens that aren't names; stripped before comparing authors so "Acemoglu et al."
# still matches "Daron Acemoglu".
_NAME_STOP = {"et", "al", "and", "the", "de", "van", "von"}


class AttributionIssue(NamedTuple):
    """A matched row whose 作者/年份 contradicts the real paper's metadata."""

    title: str  # the matrix row (matched paper) the issue is on
    claimed: str  # what the matrix says
    actual: str  # what the metadata says


@dataclass
class VerificationResult:
    checked: bool = True  # False when no 文獻矩陣 table could be parsed
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_titles: list[str] = field(default_factory=list)  # rows with no source paper
    missing_papers: list[str] = field(default_factory=list)  # papers absent from the matrix
    # Content-level issues on rows that *did* match a paper:
    author_mismatches: list[AttributionIssue] = field(default_factory=list)  # 張冠李戴
    year_mismatches: list[AttributionIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.checked and not (
            self.unmatched_titles or self.author_mismatches or self.year_mismatches
        )


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
    author_mismatches: list[AttributionIssue] = []
    year_mismatches: list[AttributionIssue] = []

    for row in rows:
        raw_title = row.get(TITLE_COLUMN) or _first_value(row)
        title = (raw_title or "(空白列)").strip()
        idx = _best_match(normalize_title(raw_title), paper_keys)
        if idx is None:
            unmatched.append(title)
            continue
        matched += 1
        matched_paper_idx.add(idx)

        # Row maps to a real paper; now check the row's content against that
        # paper's actual metadata (free, no API).
        paper = papers[idx]
        claimed_author = _column(row, _AUTHOR_COLUMN)
        if claimed_author and not _author_consistent(claimed_author, paper.get("authors")):
            author_mismatches.append(
                AttributionIssue(title, claimed_author, _format_authors(paper.get("authors")))
            )
        claimed_year = _column(row, _YEAR_COLUMN)
        if _year_conflicts(claimed_year, paper.get("year")):
            year_mismatches.append(AttributionIssue(title, claimed_year, str(paper.get("year"))))

    missing = [
        papers[i].get("title", "") for i in range(len(papers)) if i not in matched_paper_idx
    ]
    return VerificationResult(
        checked=True,
        total_rows=len(rows),
        matched_rows=matched,
        unmatched_titles=unmatched,
        missing_papers=missing,
        author_mismatches=author_mismatches,
        year_mismatches=year_mismatches,
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


def _column(row: dict[str, str], keyword: str) -> str:
    """Value of the first column whose header contains `keyword` (e.g. 「作者」,
    「年」), so a header like 「年份」 or 「第一作者」 still resolves."""
    for header, value in row.items():
        if keyword in header:
            return (value or "").strip()
    return ""


def _name_tokens(name: str) -> set[str]:
    """Lowercased Latin name tokens (len ≥ 2, sans initials/stopwords).

    Only Latin tokens are returned: papers from these English corpora carry
    romanized author names and the model transcribes those, so comparing in Latin
    is reliable; CJK tokens are ignored rather than risk a script-mismatch
    false-positive."""
    if not name:
        return set()
    tokens: set[str] = set()
    for raw in re.split(r"[^0-9A-Za-z]+", name.lower()):
        if len(raw) < 2 or raw in _NAME_STOP:
            continue  # drops single-letter initials ("d.") and "et"/"al"/...
        tokens.add(raw)
    return tokens


def _author_consistent(claimed: str, authors) -> bool:
    """True unless the row's author shares NO name token with any real author of
    the matched paper — a strong 張冠李戴 signal, not a cosmetic diff.

    Fail-safe toward *not* flagging: if either side has no comparable Latin token
    (only initials, or a CJK-only name), it returns True (can't judge → don't
    accuse)."""
    if not authors:
        return True
    claimed_tokens = _name_tokens(claimed)
    if not claimed_tokens:
        return True
    paper_tokens: set[str] = set()
    for a in authors:
        paper_tokens |= _name_tokens(str(a))
    if not paper_tokens:
        return True
    return bool(claimed_tokens & paper_tokens)


def _format_authors(authors) -> str:
    if not authors:
        return "（清單未提供作者）"
    names = [str(a).strip() for a in authors if str(a).strip()]
    if not names:
        return "（清單未提供作者）"
    return "、".join(names[:3]) + (" 等" if len(names) > 3 else "")


def _extract_year(text: str) -> int | None:
    m = re.search(r"(?:19|20)\d{2}", text or "")
    return int(m.group()) if m else None


def _year_conflicts(claimed: str, actual) -> bool:
    """True only when both sides carry a parseable 4-digit year and they differ."""
    cy = _extract_year(claimed)
    ay = _extract_year("" if actual is None else str(actual))
    return cy is not None and ay is not None and cy != ay
