"""FastAPI backend for the research-agent web frontend (web/).

Wraps the existing search -> analyze -> report pipeline as HTTP endpoints,
and exposes saved reports for the dashboard. Job state lives in an in-memory
dict — fine for a single-user local tool, cleared on restart.
"""

import os
import time
import uuid
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

from research_agent.analyzer import DEFAULT_MODEL, analyze
from research_agent.citations import write_exports
from research_agent.query import (
    SPARSE_RESULT_THRESHOLD,
    suggest_academic_terms,
    suggest_keywords,
    translate_to_english_query,
)
from research_agent.relevance import filter_by_relevance
from research_agent.report import build_report, unique_report_path
from research_agent.report_parser import (
    SECTION_ORDER,
    find_reports,
    parse_markdown_table,
    parse_report,
    year_distribution,
)
from research_agent.sources import SearchError, search
from research_agent.verify import verify_matrix

load_dotenv()

app = FastAPI(title="research-agent API")
app.add_middleware(
    CORSMiddleware,
    # Matches localhost and any private-LAN IPv4 address on port 3000, so the
    # frontend also works when opened from another device on the same Wi-Fi.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):3000",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_token(request: Request, call_next):
    # Opt-in: if RESEARCH_AGENT_TOKEN isn't set, behave exactly as before
    # (no auth — fine for localhost-only use). Once the server is exposed to
    # the LAN (research-agent-view binds 0.0.0.0), a token is generated so
    # other devices on the same Wi-Fi can't trigger paid Claude API calls.
    expected = os.environ.get("RESEARCH_AGENT_TOKEN")
    # Skip CORS preflight (OPTIONS): the browser never attaches the token header
    # to a preflight, so checking it here would 401 the preflight before
    # CORSMiddleware can answer it. That silently blocks every cross-origin
    # /api call the dashboard makes (it then shows "no reports yet"). The real
    # GET/POST that follows is still token-checked below.
    if expected and request.method != "OPTIONS" and request.url.path.startswith("/api/"):
        # Header for fetch() calls; query param fallback for plain <a href>
        # downloads, which can't attach custom headers.
        got = request.headers.get("x-api-token") or request.query_params.get("token")
        if got != expected:
            return JSONResponse(status_code=401, content={"detail": "missing or invalid token"})
    return await call_next(request)

JobStatus = Literal["searching", "analyzing", "writing", "done", "error"]
JOB_TTL_SECONDS = 1800


class Job(BaseModel):
    status: JobStatus
    message: str = ""
    report_filename: str | None = None
    created_at: float = 0.0
    suggestions: list[str] | None = None


class SearchRequest(BaseModel):
    keyword: str
    limit: int = 20
    model: str = DEFAULT_MODEL
    sort: Literal["relevance", "citations"] = "relevance"
    min_citations: int = 0
    year_from: int | None = None
    # Default-on: dual-query (original + English) for non-ASCII keywords, and a
    # Haiku relevance gate before analysis. Both add only a cheap Haiku call.
    translate: bool = True
    relevance_filter: bool = True


class TermSuggestRequest(BaseModel):
    keyword: str


jobs: dict[str, Job] = {}


def _reports_folder() -> Path:
    override = os.environ.get("REPORTS_DIR")
    return Path(override) if override else Path.cwd()


def _set_job(
    job_id: str,
    status: JobStatus,
    message: str = "",
    report_filename: str | None = None,
    suggestions: list[str] | None = None,
):
    existing = jobs.get(job_id)
    created_at = existing.created_at if existing else time.time()
    # Once computed, suggestions ride along through later status updates for the
    # same job unless a call explicitly overrides them.
    if suggestions is None and existing is not None:
        suggestions = existing.suggestions
    jobs[job_id] = Job(
        status=status,
        message=message,
        report_filename=report_filename,
        created_at=created_at,
        suggestions=suggestions,
    )


def _cleanup_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    expired = [job_id for job_id, job in jobs.items() if job.created_at < cutoff]
    for job_id in expired:
        del jobs[job_id]


def _report_path(filename: str) -> Path:
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="invalid filename")

    base = _reports_folder().resolve()
    for candidate_dir in (base, base / "reports"):
        path = (candidate_dir / filename).resolve()
        if path.parent == candidate_dir and path.exists():
            return path
    raise HTTPException(status_code=404, detail="report not found")


@app.get("/api/reports")
def list_reports():
    out = []
    for path in find_reports(_reports_folder()):
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_report(text)
        out.append(
            {
                "filename": path.name,
                "keyword": meta.get("關鍵字", path.stem),
                "date": meta.get("產生日期"),
                "paper_count": meta.get("分析論文數量"),
            }
        )
    return out


@app.get("/api/reports/{filename}")
def get_report(filename: str):
    path = _report_path(filename)
    text = path.read_text(encoding="utf-8")
    meta, sections = parse_report(text)

    matrix = parse_markdown_table(sections.get("文獻矩陣", "")) if "文獻矩陣" in sections else None
    counts = year_distribution(matrix) if matrix else {}

    return {
        "filename": path.name,
        "meta": meta,
        "sections": sections,
        "section_order": [t for t in SECTION_ORDER if t in sections]
        + [t for t in sections if t not in SECTION_ORDER],
        "matrix": matrix,
        "year_counts": counts,
        "raw": text,
    }


@app.delete("/api/reports/{filename}")
def delete_report(filename: str):
    path = _report_path(filename)
    path.unlink()
    return {"ok": True}


@app.get("/api/reports/{filename}/download")
def download_report(filename: str):
    path = _report_path(filename)
    return Response(
        content=path.read_bytes(),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )


_EXPORT_MEDIA = {
    "bib": "application/x-bibtex",
    "ris": "application/x-research-info-systems",
}


@app.get("/api/reports/{filename}/export/{fmt}")
def download_export(filename: str, fmt: str):
    """Serve the citation export (`.bib`/`.ris`) written next to the report. Only
    reports produced after this feature shipped have one, so 404 if it's absent."""
    if fmt not in _EXPORT_MEDIA:
        raise HTTPException(status_code=400, detail="invalid format")
    export_path = _report_path(filename).with_suffix(f".{fmt}")
    if not export_path.exists():
        raise HTTPException(status_code=404, detail="此報告沒有對應的匯出檔")
    return Response(
        content=export_path.read_bytes(),
        media_type=_EXPORT_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{export_path.name}"'},
    )


@app.post("/api/suggest-terms")
def suggest_terms(req: TermSuggestRequest):
    try:
        terms = suggest_academic_terms(req.keyword)
    except Exception as e:  # noqa: BLE001 — surface missing key / API errors as a clean 500
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"terms": [{"term": t.term, "gloss": t.gloss} for t in terms]}


def _run_search_job(
    job_id: str,
    keyword: str,
    limit: int,
    model: str,
    sort: str,
    min_citations: int,
    year_from: int | None,
    translate: bool = True,
    relevance_filter: bool = True,
):
    try:
        # Dual-query non-ASCII keywords (original + English), mirroring the CLI.
        queries = [keyword]
        translated_from = None
        if translate:
            try:
                translated = translate_to_english_query(keyword)
            except Exception:  # noqa: BLE001 — fall back to the original keyword, don't fail the job
                translated = keyword
            if translated and translated != keyword:
                queries = [keyword, translated]
                translated_from = keyword

        shown = " ＋ ".join(f"「{q}」" for q in queries)
        _set_job(job_id, "searching", f"在 Semantic Scholar、OpenAlex 搜尋 {shown}...")
        result = search(
            queries, limit=limit, sort=sort, min_citations=min_citations, year_from=year_from
        )

        suggestions = None
        if len(result.papers) < SPARSE_RESULT_THRESHOLD:
            try:
                suggestions = suggest_keywords(keyword) or None
            except Exception:  # noqa: BLE001 — suggestions are a nice-to-have, never fail the job for them
                suggestions = None

        if not result.papers:
            _set_job(
                job_id,
                "error",
                "找不到含摘要的相關論文，請換個關鍵字試試。",
                suggestions=suggestions,
            )
            return
        papers = result.papers

        # Relevance gate before the paid analysis (keeps all on any failure).
        relevance = None
        if relevance_filter:
            relevance = filter_by_relevance(keyword, papers)
            if relevance.checked:
                papers = relevance.kept

        sparse_note = f"（只找到 {len(papers)} 篇，可參考下方建議關鍵字。）" if suggestions else ""

        _set_job(
            job_id,
            "analyzing",
            f"使用 Claude ({model}) 分析 {len(papers)} 篇論文...{sparse_note}",
            suggestions=suggestions,
        )
        analysis = analyze(keyword, papers, model=model)
        verification = verify_matrix(analysis, papers)

        _set_job(job_id, "writing", "正在產生報告...")
        report = build_report(
            keyword,
            len(papers),
            analysis,
            queries=queries,
            translated_from=translated_from,
            sort=sort,
            min_citations=min_citations,
            year_from=year_from,
            model=model,
            stats=result,
            verification=verification,
            papers=papers,
            relevance=relevance,
        )
        out_path = unique_report_path(_reports_folder(), keyword)
        out_path.write_text(report, encoding="utf-8")
        write_exports(out_path, papers)

        _set_job(job_id, "done", f"完成！{sparse_note}", report_filename=out_path.name)
    except (SearchError, RuntimeError) as e:
        _set_job(job_id, "error", str(e))


@app.post("/api/search")
def start_search(req: SearchRequest, background_tasks: BackgroundTasks):
    _cleanup_jobs()
    job_id = str(uuid.uuid4())
    _set_job(job_id, "searching", "排隊中...")
    background_tasks.add_task(
        _run_search_job,
        job_id,
        req.keyword,
        req.limit,
        req.model,
        req.sort,
        req.min_citations,
        req.year_from,
        req.translate,
        req.relevance_filter,
    )
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    _cleanup_jobs()
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
