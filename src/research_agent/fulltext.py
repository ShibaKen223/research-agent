"""Opt-in, bounded full-text extraction for the open-access subset.

The rest of the pipeline is abstract-only — no stated methods, no stated
limitations — because an abstract systematically omits them and tends to *spin*
the result. This module narrows that ceiling **for OA papers only**: it finds an
open-access PDF (arXiv directly, or Unpaywall by DOI), pulls the text, and runs a
single Haiku batch to extract each paper's own stated methods + limitations.

What it deliberately does NOT do: appraise methodological quality, compute effect
sizes, assess risk-of-bias, or read paywalled papers. It surfaces what the authors
themselves wrote, so the reader has more than the (spun) abstract to weigh — it
does not certify anything.

Bounded by design (the API budget is tight): only the first `MAX_FULLTEXT` OA
papers are processed; only a short methods/limitations excerpt is sent to the model
(never the whole paper); the result is cached and **fail-open** exactly like
`relevance.py` / `claim_check.py` — any missing key, missing `pypdf`, network, or
parse error degrades to "not checked" rather than raising or altering the run.

PDF text extraction is best-effort: complex two-column layouts can come out
jumbled, in which case the model is told to return empty fields rather than guess.
"""

import io
import json
import os
from dataclasses import dataclass, field
from typing import NamedTuple

import requests

from research_agent import cache

FULLTEXT_MODEL = "claude-haiku-4-5-20251001"
ARXIV_SOURCE = "arXiv"

# Bounds (cost + safety). Only this many OA papers are fetched per run; each PDF is
# size/page capped; only a short excerpt per paper reaches the model.
MAX_FULLTEXT = 8
PDF_MAX_BYTES = 8 * 1024 * 1024
PDF_MAX_PAGES = 30
EXCERPT_CHARS = 1500
MAX_TOKENS = 1500
_HTTP_TIMEOUT = 30
HEADERS = {"User-Agent": "research-agent/0.1.0 (https://github.com/research-agent)"}

# Section cues we try to locate in the extracted text, in priority order. Limitations
# are the most valuable (and the most absent from abstracts), so they come first.
_LIMITATION_CUES = ("limitation", "future work", "future research", "研究限制", "限制")
_METHOD_CUES = ("materials and methods", "methodology", "method", "研究方法", "資料與方法")


class FullTextNote(NamedTuple):
    title: str
    methods: str  # the paper's own stated method/design ("" if not found)
    limitations: str  # the authors' own stated limitations ("" if not found)


@dataclass
class FullTextResult:
    checked: bool = True  # False when it didn't run (off / no key / no OA text / error)
    notes: list[FullTextNote] = field(default_factory=list)
    attempted: int = 0  # OA PDFs we tried to fetch
    model: str = FULLTEXT_MODEL


_PROMPT = """\
You are extracting two things from each paper's OWN text (an excerpt of the full \
paper, NOT the abstract): its METHODS (study design / data / approach, <=25 words) \
and the authors' stated LIMITATIONS (<=30 words).

Use ONLY the given excerpt. If the excerpt does not clearly contain a field (or is \
too garbled to read), return an empty string "" for it. Do NOT infer or invent.

Output ONLY a JSON object mapping each item's number (as a string) to an object \
{{"methods": "...", "limitations": "..."}}. No prose, no code fence.

{items_block}
"""


def extract_fulltext_notes(
    papers: list[dict], model: str = FULLTEXT_MODEL, email: str | None = None
) -> FullTextResult:
    """For up to `MAX_FULLTEXT` open-access papers, fetch the PDF and extract the
    authors' stated methods + limitations. Returns a `FullTextResult`;
    `checked=False` when nothing could be fetched/extracted or the call couldn't run
    — never raises, never alters `papers`."""
    email = email or os.environ.get("UNPAYWALL_EMAIL") or os.environ.get("OPENALEX_MAILTO")

    items: list[tuple[str, str]] = []  # (title, excerpt)
    attempted = 0
    for paper in papers:
        if len(items) >= MAX_FULLTEXT:
            break
        url = resolve_pdf_url(paper, email=email)
        if not url:
            continue
        attempted += 1
        data = download_pdf(url)
        if not data:
            continue
        excerpt = find_relevant_excerpt(pdf_to_text(data))
        if excerpt:
            items.append(((paper.get("title") or "Untitled").strip(), excerpt))

    if not items:
        return FullTextResult(checked=False, attempted=attempted, model=model)

    prompt = _PROMPT.format(items_block=_items_block(items))

    ck = cache.key("fulltext", model, prompt)
    cached = cache.get("fulltext", ck)
    if cached is not None:
        notes = _coerce_notes(cached, items)
        if notes is not None:
            return FullTextResult(checked=True, notes=notes, attempted=attempted, model=model)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return FullTextResult(checked=False, attempted=attempted, model=model)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in message.content if b.type == "text").strip()
        parsed = _parse_notes(text, len(items))
    except Exception:  # noqa: BLE001 — any failure degrades to "not checked"
        return FullTextResult(checked=False, attempted=attempted, model=model)

    if parsed is None:
        return FullTextResult(checked=False, attempted=attempted, model=model)

    cache.set("fulltext", ck, parsed)
    return FullTextResult(
        checked=True, notes=_build_notes(parsed, items), attempted=attempted, model=model
    )


# --- OA PDF discovery ---------------------------------------------------------

def resolve_pdf_url(paper: dict, *, email: str | None = None) -> str | None:
    """An open-access PDF URL for `paper`, or None. arXiv is resolved directly (no
    extra call); anything else with a DOI is looked up via Unpaywall (needs an
    email — `UNPAYWALL_EMAIL`/`OPENALEX_MAILTO` — and skipped without one)."""
    return _arxiv_pdf_url(paper) or _unpaywall_pdf_url((paper.get("doi") or "").strip(), email)


def _arxiv_pdf_url(paper: dict) -> str | None:
    url = (paper.get("url") or "").strip()
    is_arxiv = (paper.get("source") or "") == ARXIV_SOURCE or "arxiv.org/abs/" in url
    if not is_arxiv:
        return None
    pid = (paper.get("paper_id") or "").strip()
    if not pid and "/abs/" in url:
        pid = url.rsplit("/abs/", 1)[-1]
    return f"https://arxiv.org/pdf/{pid}" if pid else None


def _unpaywall_pdf_url(doi: str, email: str | None) -> str | None:
    if not doi or not email:
        return None
    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": email},
            headers=HEADERS,
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return best["url_for_pdf"]
    for loc in data.get("oa_locations") or []:
        if loc.get("url_for_pdf"):
            return loc["url_for_pdf"]
    return None


def download_pdf(url: str) -> bytes | None:
    """Download a PDF (size-capped, magic-byte checked). Returns None on any error
    or if the response isn't actually a PDF (e.g. a landing page returning HTML)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=_HTTP_TIMEOUT, stream=True)
        if resp.status_code != 200:
            return None
        data = b""
        for chunk in resp.iter_content(8192):
            data += chunk
            if len(data) > PDF_MAX_BYTES:
                return None
    except requests.RequestException:
        return None
    return data if data[:5] == b"%PDF-" else None


def pdf_to_text(data: bytes) -> str:
    """Extract text from PDF bytes with pypdf (a capped number of pages). Returns ""
    if pypdf isn't installed (it's an optional dependency) or parsing fails — the
    caller treats no text as "nothing to extract", never an error."""
    try:
        import pypdf
    except ImportError:
        return ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = reader.pages[:PDF_MAX_PAGES]
        return "\n".join((page.extract_text() or "") for page in pages)
    except Exception:  # noqa: BLE001 — any pypdf failure → no text
        return ""


def find_relevant_excerpt(text: str) -> str:
    """A small, targeted excerpt (limitations first, then methods) from the full
    text, so only a bounded chunk reaches the model. Pure/offline (unit-tested).
    Returns "" when no cue is found, so a paper with no locatable section is simply
    skipped rather than summarised from arbitrary text."""
    if not text:
        return ""
    low = text.lower()
    windows: list[str] = []
    for cue in _LIMITATION_CUES:
        i = low.find(cue)
        if i != -1:
            windows.append(text[i : i + 900])
            break
    for cue in _METHOD_CUES:
        i = low.find(cue)
        if i != -1:
            windows.append(text[i : i + 600])
            break
    excerpt = "\n…\n".join(w.strip() for w in windows if w.strip())
    return excerpt[:EXCERPT_CHARS]


# --- model I/O ----------------------------------------------------------------

def _items_block(items: list[tuple[str, str]]) -> str:
    out = []
    for i, (_title, excerpt) in enumerate(items):
        ex = " ".join(excerpt.split())
        out.append(f"[{i}] EXCERPT: {ex}")
    return "\n\n".join(out)


def _build_notes(parsed: dict, items: list[tuple[str, str]]) -> list[FullTextNote]:
    notes: list[FullTextNote] = []
    for i, (title, _excerpt) in enumerate(items):
        entry = parsed.get(str(i)) or {}
        methods = str(entry.get("methods") or "").strip()
        limitations = str(entry.get("limitations") or "").strip()
        if methods or limitations:
            notes.append(FullTextNote(title, methods, limitations))
    return notes


def _coerce_notes(cached, items: list[tuple[str, str]]) -> list[FullTextNote] | None:
    """Rebuild notes from a cached parse (JSON round-trip keeps the string keys we
    stored). Returns None if the cache is unusable, so the caller recomputes."""
    if not isinstance(cached, dict):
        return None
    return _build_notes(cached, items)


def _parse_notes(text: str, n: int) -> dict | None:
    """Pull the {index: {methods, limitations}} JSON out of the reply, tolerating a
    stray code fence or surrounding prose. Returns None if nothing usable."""
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
    out: dict[str, dict] = {}
    for k, v in raw.items():
        try:
            idx = int(str(k).strip())
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < n) or not isinstance(v, dict):
            continue
        out[str(idx)] = {
            "methods": str(v.get("methods") or "").strip(),
            "limitations": str(v.get("limitations") or "").strip(),
        }
    return out or None
