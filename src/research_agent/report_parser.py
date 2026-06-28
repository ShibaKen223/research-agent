"""Shared, pandas-free parsing helpers for research-agent reports.

Used by the FastAPI backend (api.py), so the markdown report format only
needs to be understood in one place.
"""

import re
from collections import Counter
from pathlib import Path

SECTION_ORDER = ["文獻矩陣", "研究趨勢", "研究缺口", "碩論題目建議"]


def find_reports(folder: Path) -> list[Path]:
    paths = list(folder.glob("*_report.md")) + list(folder.glob("reports/*.md"))
    return sorted(set(paths), key=lambda p: p.stat().st_mtime, reverse=True)


def parse_report(text: str) -> tuple[dict, dict]:
    """Split a report into (meta dict, {section_title: section_body})."""
    meta = {}
    for key, pattern in [
        ("關鍵字", r"# 研究分析報告：(.+)"),
        ("產生日期", r"產生日期：(.+)"),
        ("分析論文數量", r"分析論文數量：(.+)"),
        ("資料來源", r"資料來源：(.+)"),
    ]:
        m = re.search(pattern, text)
        if m:
            meta[key] = m.group(1).strip()

    sections = {}
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    for title, body in zip(parts[1::2], parts[2::2]):
        sections[title.strip()] = body.strip(" \n-")
    return meta, sections


def parse_markdown_table(body: str) -> list[dict[str, str]] | None:
    """Pull the first markdown table out of a section body, if any."""
    lines = [l for l in body.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        return None
    rows = [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in lines
        if not re.fullmatch(r"[\s|:-]+", line)
    ]
    if len(rows) < 2:
        return None
    header, *data = rows
    data = [r for r in data if len(r) == len(header)]
    if not data:
        return None
    return [dict(zip(header, row)) for row in data]


def year_distribution(rows: list[dict[str, str]], year_field: str = "年份") -> dict[str, int]:
    """Count rows per year, e.g. for the 文獻矩陣 table. Keys are sorted ascending."""
    counts = Counter(row[year_field].strip() for row in rows if row.get(year_field, "").strip())
    return dict(sorted(counts.items()))
