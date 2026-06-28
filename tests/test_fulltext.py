"""Offline unit tests for fulltext.py (no API, no network).

Covers the pure pieces: OA-PDF URL resolution, the limitations/methods excerpt
heuristic, model-reply parsing, note building, and the fail-open paths. The
network + Haiku orchestration (`extract_fulltext_notes`) is integration-only.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent import fulltext  # noqa: E402


# --- arXiv PDF URL -----------------------------------------------------------

def test_arxiv_pdf_url_from_source():
    p = {"source": "arXiv", "paper_id": "2308.01899v1", "url": "http://arxiv.org/abs/2308.01899v1"}
    assert fulltext._arxiv_pdf_url(p) == "https://arxiv.org/pdf/2308.01899v1"


def test_arxiv_pdf_url_from_url_when_source_differs():
    p = {"source": "OpenAlex", "url": "https://arxiv.org/abs/1234.5678", "paper_id": ""}
    assert fulltext._arxiv_pdf_url(p) == "https://arxiv.org/pdf/1234.5678"


def test_arxiv_pdf_url_none_for_non_arxiv():
    p = {"source": "OpenAlex", "url": "https://doi.org/10.1/x", "paper_id": "W123"}
    assert fulltext._arxiv_pdf_url(p) is None


# --- resolve_pdf_url (no network) --------------------------------------------

def test_resolve_pdf_url_arxiv_needs_no_email():
    assert fulltext.resolve_pdf_url({"source": "arXiv", "paper_id": "2001.00001"}) == (
        "https://arxiv.org/pdf/2001.00001"
    )


def test_resolve_pdf_url_non_arxiv_without_email_is_none():
    # No email => no Unpaywall call => None, without touching the network.
    p = {"source": "OpenAlex", "doi": "10.1/x", "url": "https://x"}
    assert fulltext.resolve_pdf_url(p, email=None) is None


# --- excerpt heuristic -------------------------------------------------------

def test_find_excerpt_picks_limitations_and_methods():
    text = (
        "Intro paragraph. " * 4
        + "Methods We used a randomized controlled trial with 200 participants. "
        + "Results were positive. "
        + "Limitations This study is limited by its small sample and single site. "
        + "Conclusion done."
    )
    ex = fulltext.find_relevant_excerpt(text).lower()
    assert "small sample" in ex
    assert "randomized controlled trial" in ex


def test_find_excerpt_empty_when_no_cues():
    assert fulltext.find_relevant_excerpt("random prose with no recognizable sections") == ""


def test_find_excerpt_empty_on_empty():
    assert fulltext.find_relevant_excerpt("") == ""


# --- model reply parsing -----------------------------------------------------

def test_parse_notes_valid():
    out = fulltext._parse_notes('{"0": {"methods": "RCT", "limitations": "small n"}}', 1)
    assert out == {"0": {"methods": "RCT", "limitations": "small n"}}


def test_parse_notes_strips_code_fence_and_prose():
    reply = 'Here you go:\n```json\n{"0": {"methods": "survey", "limitations": ""}}\n```'
    out = fulltext._parse_notes(reply, 1)
    assert out["0"]["methods"] == "survey"


def test_parse_notes_drops_out_of_range():
    out = fulltext._parse_notes(
        '{"0": {"methods":"a","limitations":"b"}, "5": {"methods":"x","limitations":"y"}}', 1
    )
    assert set(out.keys()) == {"0"}


def test_parse_notes_none_on_garbage():
    assert fulltext._parse_notes("not json at all", 1) is None


# --- note building + fail-open ----------------------------------------------

def test_build_notes_skips_all_empty_fields():
    parsed = {"0": {"methods": "", "limitations": ""}, "1": {"methods": "RCT", "limitations": ""}}
    items = [("Paper A", "ex"), ("Paper B", "ex")]
    notes = fulltext._build_notes(parsed, items)
    assert len(notes) == 1
    assert notes[0].title == "Paper B" and notes[0].methods == "RCT"


def test_pdf_to_text_failopen_on_non_pdf_bytes():
    assert fulltext.pdf_to_text(b"this is definitely not a pdf") == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
