"""Build a citable reference list + BibTeX/RIS exports from the real paper metadata.

The 文獻矩陣 is written by Claude, so it deliberately must NOT carry DOIs — asking
the model to transcribe identifiers is exactly how citation errors creep in. The
DOI / venue / URL are, however, already fetched and de-duplicated for every paper
(see each source's `_normalize`), so this module emits them straight from that
ground-truth metadata: a numbered `## 參考文獻` section, plus `.bib`/`.ris` files
the user can import into Zotero / EndNote / a reference manager. Zero API cost and,
because nothing is model-generated, zero hallucination risk.
"""

from research_agent.text_utils import normalize_title

REFERENCES_SECTION = "參考文獻"


def _doi_url(paper: dict) -> str:
    doi = (paper.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    return (paper.get("url") or "").strip()


def _authors_label(authors: list[str], *, max_shown: int = 3) -> str:
    authors = [a for a in (authors or []) if a]
    if not authors:
        return "(作者未提供)"
    if len(authors) > max_shown:
        return ", ".join(authors[:max_shown]) + ", et al."
    return ", ".join(authors)


def reference_list_markdown(papers: list[dict]) -> str:
    """Render the authoritative `## 參考文獻` section: a numbered, linkable list so
    the report can actually be cited without re-searching every paper by hand."""
    lines = [f"## {REFERENCES_SECTION}", ""]
    for i, p in enumerate(papers, start=1):
        authors = _authors_label(p.get("authors") or [])
        year = p.get("year") or "n.d."
        title = (p.get("title") or "Untitled").strip()
        venue = (p.get("venue") or "").strip()
        link = _doi_url(p)

        parts = [f"{i}. {authors} ({year}). *{title}*."]
        if venue:
            parts.append(f" {venue}.")
        if link:
            parts.append(f" {link}")
        lines.append("".join(parts))
    lines.append("")
    return "\n".join(lines)


def _cite_key(paper: dict, index: int, used: set[str]) -> str:
    """A stable, unique BibTeX key: firstauthorsurname + year (+ a/b/... on clash)."""
    authors = [a for a in (paper.get("authors") or []) if a]
    surname = ""
    if authors:
        first = authors[0].strip()
        # "Last, First" -> surname before the comma; "First Last" -> last token.
        surname = first.split(",")[0].strip() if "," in first else first.split()[-1]
    surname = "".join(ch for ch in surname.lower() if ch.isalnum()) or "ref"
    year = str(paper.get("year") or "nd")
    base = f"{surname}{year}"
    candidate = base
    suffix = ord("a")
    while candidate in used:
        candidate = f"{base}{chr(suffix)}"
        suffix += 1
    used.add(candidate)
    return candidate


def _bibtex_escape(value: str) -> str:
    return (value or "").replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")


def to_bibtex(papers: list[dict]) -> str:
    """Serialize the papers as a BibTeX file (one @article entry each)."""
    used: set[str] = set()
    entries = []
    for i, p in enumerate(papers):
        key = _cite_key(p, i, used)
        fields = [("title", (p.get("title") or "").strip())]
        authors = [a for a in (p.get("authors") or []) if a]
        if authors:
            fields.append(("author", " and ".join(authors)))
        if p.get("year"):
            fields.append(("year", str(p["year"])))
        if (p.get("venue") or "").strip():
            fields.append(("journal", p["venue"].strip()))
        if (p.get("doi") or "").strip():
            fields.append(("doi", p["doi"].strip()))
        link = _doi_url(p)
        if link:
            fields.append(("url", link))

        body = ",\n".join(f"  {name} = {{{_bibtex_escape(val)}}}" for name, val in fields)
        entries.append(f"@article{{{key},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def to_ris(papers: list[dict]) -> str:
    """Serialize the papers as an RIS file (EndNote / Zotero import format)."""
    records = []
    for p in papers:
        lines = ["TY  - JOUR"]
        for author in (p.get("authors") or []):
            if author:
                lines.append(f"AU  - {author}")
        if (p.get("title") or "").strip():
            lines.append(f"TI  - {p['title'].strip()}")
        if p.get("year"):
            lines.append(f"PY  - {p['year']}")
        if (p.get("venue") or "").strip():
            lines.append(f"JO  - {p['venue'].strip()}")
        if (p.get("doi") or "").strip():
            lines.append(f"DO  - {p['doi'].strip()}")
        link = _doi_url(p)
        if link:
            lines.append(f"UR  - {link}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records) + ("\n" if records else "")


def write_exports(report_path, papers: list[dict]) -> list:
    """Write `<report>.bib` and `<report>.ris` next to the report. Returns the paths
    written (empty list if there were no papers). Best-effort: never the reason a
    run fails."""
    from pathlib import Path

    report_path = Path(report_path)
    if not papers:
        return []
    written = []
    for suffix, builder in ((".bib", to_bibtex), (".ris", to_ris)):
        path = report_path.with_suffix(suffix)
        try:
            path.write_text(builder(papers), encoding="utf-8")
            written.append(path)
        except OSError:
            pass
    return written


# Title key kept importable here so callers matching matrix rows to references
# use the same normalization as the rest of the pipeline.
__all__ = [
    "REFERENCES_SECTION",
    "reference_list_markdown",
    "to_bibtex",
    "to_ris",
    "write_exports",
    "normalize_title",
]
