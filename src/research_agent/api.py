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
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from research_agent.analyzer import DEFAULT_MODEL, analyze
from research_agent.query import SPARSE_RESULT_THRESHOLD, suggest_keywords, translate_to_english_query
from research_agent.report import build_report, unique_report_path
from research_agent.report_parser import (
    SECTION_ORDER,
    find_reports,
    parse_markdown_table,
    parse_report,
    year_distribution,
)
from research_agent.semantic_scholar import SemanticScholarError, search_papers

load_dotenv()

app = FastAPI(title="research-agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    translate: bool = False


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


def _run_search_job(
    job_id: str,
    keyword: str,
    limit: int,
    model: str,
    sort: str,
    min_citations: int,
    year_from: int | None,
    translate: bool = False,
):
    try:
        query = keyword
        translated_from = None
        if translate:
            try:
                query = translate_to_english_query(keyword)
            except Exception:  # noqa: BLE001 — fall back to the original keyword, don't fail the job
                query = keyword
            if query != keyword:
                translated_from = keyword

        _set_job(job_id, "searching", f"在 Semantic Scholar 搜尋「{query}」...")
        result = search_papers(
            query, limit=limit, sort=sort, min_citations=min_citations, year_from=year_from
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
        sparse_note = f"（只找到 {len(papers)} 篇，可參考下方建議關鍵字。）" if suggestions else ""

        _set_job(
            job_id,
            "analyzing",
            f"使用 Claude ({model}) 分析 {len(papers)} 篇論文...{sparse_note}",
            suggestions=suggestions,
        )
        analysis = analyze(keyword, papers, model=model)

        _set_job(job_id, "writing", "正在產生報告...")
        report = build_report(
            keyword,
            len(papers),
            analysis,
            query=query,
            translated_from=translated_from,
            sort=sort,
            min_citations=min_citations,
            year_from=year_from,
            model=model,
            stats=result,
        )
        out_path = unique_report_path(_reports_folder(), keyword)
        out_path.write_text(report, encoding="utf-8")

        _set_job(job_id, "done", f"完成！{sparse_note}", report_filename=out_path.name)
    except SemanticScholarError as e:
        _set_job(job_id, "error", str(e))
    except RuntimeError as e:
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
    )
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    _cleanup_jobs()
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
