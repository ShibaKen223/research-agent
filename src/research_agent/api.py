"""FastAPI backend for the research-agent web frontend (web/).

Wraps the existing search -> analyze -> report pipeline as HTTP endpoints,
and exposes saved reports for the dashboard. Job state lives in an in-memory
dict — fine for a single-user local tool, cleared on restart.
"""

import uuid
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from research_agent.analyzer import DEFAULT_MODEL, analyze
from research_agent.report import build_report
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


class Job(BaseModel):
    status: JobStatus
    message: str = ""
    report_filename: str | None = None


class SearchRequest(BaseModel):
    keyword: str
    limit: int = 20
    model: str = DEFAULT_MODEL


jobs: dict[str, Job] = {}


def _reports_folder() -> Path:
    return Path.cwd()


def _report_path(filename: str) -> Path:
    path = (_reports_folder() / filename).resolve()
    if path.parent != _reports_folder().resolve() or not path.name.endswith(".md"):
        raise HTTPException(status_code=400, detail="invalid filename")
    if not path.exists():
        raise HTTPException(status_code=404, detail="report not found")
    return path


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


def _run_search_job(job_id: str, keyword: str, limit: int, model: str):
    try:
        jobs[job_id] = Job(status="searching", message=f"在 Semantic Scholar 搜尋「{keyword}」...")
        papers = search_papers(keyword, limit=limit)
        if not papers:
            jobs[job_id] = Job(status="error", message="找不到含摘要的相關論文，請換個關鍵字試試。")
            return

        jobs[job_id] = Job(status="analyzing", message=f"使用 Claude ({model}) 分析 {len(papers)} 篇論文...")
        analysis = analyze(keyword, papers, model=model)

        jobs[job_id] = Job(status="writing", message="正在產生報告...")
        report = build_report(keyword, len(papers), analysis)
        out_path = _reports_folder() / f"{keyword}_report.md"
        out_path.write_text(report, encoding="utf-8")

        jobs[job_id] = Job(status="done", message="完成！", report_filename=out_path.name)
    except SemanticScholarError as e:
        jobs[job_id] = Job(status="error", message=str(e))
    except RuntimeError as e:
        jobs[job_id] = Job(status="error", message=str(e))


@app.post("/api/search")
def start_search(req: SearchRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = Job(status="searching", message="排隊中...")
    background_tasks.add_task(_run_search_job, job_id, req.keyword, req.limit, req.model)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
