"""Offline unit tests for the deterministic citation builders (no API, no network)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import citations  # noqa: E402


def _paper(**over):
    base = {
        "title": "Deep Learning for X",
        "authors": ["Alice Lin", "Bob Wang"],
        "year": 2021,
        "venue": "NeurIPS",
        "doi": "10.1/abc",
        "url": "https://example.org/x",
    }
    base.update(over)
    return base


# --- reference list -----------------------------------------------------------

def test_reference_list_has_heading_and_numbered_entries():
    md = citations.reference_list_markdown([_paper(), _paper(title="Second")])
    assert md.startswith("## 參考文獻")
    assert "1. " in md and "2. " in md
    assert "*Deep Learning for X*" in md
    assert "NeurIPS" in md


def test_reference_uses_doi_link_then_falls_back_to_url():
    with_doi = citations.reference_list_markdown([_paper()])
    assert "https://doi.org/10.1/abc" in with_doi
    no_doi = citations.reference_list_markdown([_paper(doi="")])
    assert "https://example.org/x" in no_doi


def test_reference_collapses_many_authors_with_et_al():
    md = citations.reference_list_markdown(
        [_paper(authors=["A One", "B Two", "C Three", "D Four"])]
    )
    assert "et al." in md


def test_reference_handles_missing_fields():
    md = citations.reference_list_markdown([{"title": "Bare"}])
    assert "*Bare*" in md
    assert "n.d." in md  # missing year
    assert "(作者未提供)" in md


# --- BibTeX -------------------------------------------------------------------

def test_bibtex_emits_article_entry_with_fields():
    bib = citations.to_bibtex([_paper()])
    assert bib.startswith("@article{")
    assert "title = {Deep Learning for X}" in bib
    assert "author = {Alice Lin and Bob Wang}" in bib
    assert "year = {2021}" in bib
    assert "doi = {10.1/abc}" in bib


def test_bibtex_keys_are_unique_on_collision():
    bib = citations.to_bibtex([_paper(), _paper(title="Other")])
    # Same first author + year would collide; the second gets a suffix.
    assert "@article{lin2021," in bib
    assert "@article{lin2021a," in bib


# --- RIS ----------------------------------------------------------------------

def test_ris_has_required_tags():
    ris = citations.to_ris([_paper()])
    assert "TY  - JOUR" in ris
    assert "AU  - Alice Lin" in ris
    assert "TI  - Deep Learning for X" in ris
    assert "PY  - 2021" in ris
    assert ris.rstrip().endswith("ER  -")


# --- write_exports ------------------------------------------------------------

def test_write_exports_creates_sibling_files():
    with tempfile.TemporaryDirectory() as d:
        report = Path(d) / "topic_report.md"
        report.write_text("# report", encoding="utf-8")
        written = citations.write_exports(report, [_paper()])
        names = {p.name for p in written}
        assert names == {"topic_report.bib", "topic_report.ris"}
        assert (Path(d) / "topic_report.bib").exists()


def test_write_exports_noop_without_papers():
    with tempfile.TemporaryDirectory() as d:
        report = Path(d) / "topic_report.md"
        assert citations.write_exports(report, []) == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
