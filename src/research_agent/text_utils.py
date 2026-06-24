"""Small, dependency-free text helpers shared across the search sources.

Kept in their own module so `semantic_scholar`, `openalex`, `sources` and
`verify` can all normalize DOIs/titles the same way without importing each
other (which would create cycles).
"""

import re

_DOI_PREFIX = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_doi(doi: str | None) -> str:
    """Lower-case a DOI and strip any `https://doi.org/` prefix, so the same
    paper from two databases compares equal. Returns "" for a missing DOI."""
    if not doi:
        return ""
    return _DOI_PREFIX.sub("", doi.strip().lower())


def normalize_title(title: str | None) -> str:
    """Fold a title to a comparison key: lower-case, punctuation -> space,
    whitespace collapsed. Used both for cross-source de-duplication and for
    matching analysed papers back to 文獻矩陣 rows."""
    if not title:
        return ""
    return _WS.sub(" ", _PUNCT.sub(" ", title.strip().lower())).strip()
