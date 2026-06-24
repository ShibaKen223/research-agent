"""Assemble the final markdown report file."""

from datetime import date
from pathlib import Path

_SORT_LABELS = {
    "relevance": "關鍵字相關度",
    "citations": "全領域引用數（由高到低）",
}


def build_report(
    keyword: str,
    paper_count: int,
    analysis_markdown: str,
    *,
    query: str | None = None,
    translated_from: str | None = None,
    sort: str | None = None,
    min_citations: int = 0,
    year_from: int | None = None,
    model: str | None = None,
    stats=None,
    verification=None,
) -> str:
    """Assemble the final report.

    When `query` is given, a `## 檢索說明` appendix is appended documenting how
    the report was produced (databases, query, filters, model) and how many papers
    were found vs. excluded — a reproducible, auditable search record. `stats` is
    the `SearchResult` from the search (used for the exclusion/dedup/source counts).
    `translated_from`, if set, is the original keyword the `query` was auto-translated
    from, so the appendix can disclose that translation happened. `verification`,
    if set, is the `VerificationResult` from `verify.verify_matrix`, rendered as a
    `分析驗證` block so the report states whether every 文獻矩陣 row maps to a real
    retrieved paper.
    """
    header = (
        f"# 研究分析報告：{keyword}\n\n"
        f"- 產生日期：{date.today().isoformat()}\n"
        f"- 分析論文數量：{paper_count}\n"
        f"- 資料來源：Semantic Scholar\n\n"
        "---\n\n"
    )
    body = header + analysis_markdown.strip() + "\n"

    if query is not None:
        body += "\n" + _search_appendix(
            query=query,
            translated_from=translated_from,
            paper_count=paper_count,
            sort=sort,
            min_citations=min_citations,
            year_from=year_from,
            model=model,
            stats=stats,
            verification=verification,
        )
    return body


def _search_appendix(
    *, query, translated_from, paper_count, sort, min_citations, year_from, model, stats, verification
) -> str:
    """Render the `## 檢索說明` provenance section."""
    filters = []
    if year_from is not None:
        filters.append(f"{year_from} 年（含）後發表")
    if min_citations:
        filters.append(f"引用數 ≥ {min_citations}")
    filter_label = "、".join(filters) if filters else "無"

    if translated_from:
        query_line = f"- 檢索式：`{query}`（由關鍵字「{translated_from}」自動翻譯為英文）"
    else:
        query_line = f"- 檢索式：`{query}`"

    db_names = stats.databases if (stats and stats.databases) else ["Semantic Scholar"]
    db_label = "、".join(db_names)

    lines = [
        "## 檢索說明",
        "",
        "本報告的文獻來源與檢索條件如下，供查證與重現：",
        "",
        f"- 資料庫：{db_label}",
        query_line,
        f"- 檢索日期：{date.today().isoformat()}",
        f"- 排序方式：{_SORT_LABELS.get(sort or '', sort or '未指定')}",
        f"- 篩選條件：{filter_label}",
    ]
    if model:
        lines.append(f"- 分析模型：{model}（temperature=0，結果可重現）")

    if stats is not None:
        lines += ["", "檢索結果統計：", ""]
        if stats.total_matches is not None:
            lines.append(f"- 各資料庫命中估計合計：約 {stats.total_matches}")
        lines += [
            f"- 實際取回筆數：{stats.fetched}",
            f"- 因缺少摘要而排除：{stats.excluded_no_abstract}",
            f"- 因不符篩選條件而排除：{stats.excluded_by_filter}",
        ]
        if stats.excluded_duplicates:
            lines.append(f"- 跨資料庫重複而合併：{stats.excluded_duplicates}")
        lines.append(f"- 最終納入分析：{paper_count}")
        if stats.sources:
            contrib = "、".join(f"{name} {count} 篇" for name, count in stats.sources.items())
            lines.append(f"- 各來源貢獻：{contrib}")
        if stats.failed_databases:
            failed = "、".join(stats.failed_databases)
            lines.append(f"- ⚠️ 查詢失敗、未納入的資料庫：{failed}")

    if verification is not None and verification.checked:
        lines += ["", "分析驗證（程式自動核對矩陣，非模型自述）：", ""]
        lines.append(f"- 文獻矩陣列數：{verification.total_rows}")
        lines.append(f"- 可對應到實際檢索論文：{verification.matched_rows}")
        if verification.unmatched_titles:
            lines.append(
                f"- ⚠️ 無法對應、可能為杜撰的列（{len(verification.unmatched_titles)}）："
            )
            lines += [f"  - {title}" for title in verification.unmatched_titles]
        else:
            lines.append("- ✅ 矩陣中每一列都對應到實際檢索到的論文，未發現杜撰。")
        if verification.missing_papers:
            lines.append(f"- 已檢索但未列入矩陣的論文：{len(verification.missing_papers)}")

    lines += [
        "",
        "納入準則：僅納入上述資料庫提供摘要（多為英文）的論文；"
        "分析內容僅依據各論文之標題與摘要，未取用全文。"
        "因此實際符合主題但無摘要、或未被這些資料庫收錄的論文可能未納入，"
        "解讀時請留意此覆蓋範圍限制。",
        "",
    ]
    return "\n".join(lines)


def unique_report_path(folder: Path, keyword: str) -> Path:
    """Pick `{keyword}_report.md` under `folder`, or `{keyword}_2_report.md`/`_3`/...
    if it's taken, so re-running the same keyword doesn't silently overwrite an
    older report. The `_report.md` suffix is kept intact since report_parser's
    `find_reports()` globs on it."""
    base = folder / f"{keyword}_report.md"
    if not base.exists():
        return base
    i = 2
    while (candidate := folder / f"{keyword}_{i}_report.md").exists():
        i += 1
    return candidate
