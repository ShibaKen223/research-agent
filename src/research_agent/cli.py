"""research-agent: search Semantic Scholar, analyze with Claude, write a markdown report."""

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from research_agent.analyzer import DEFAULT_MODEL, analyze
from research_agent.query import SPARSE_RESULT_THRESHOLD, suggest_keywords, translate_to_english_query
from research_agent.report import build_report, unique_report_path
from research_agent.sources import SearchError, search
from research_agent.verify import verify_matrix


@click.command()
@click.argument("keyword")
@click.option("--limit", default=20, show_default=True, help="要搜尋的論文數量上限。")
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="使用的 Claude model。")
@click.option(
    "--sort",
    type=click.Choice(["relevance", "citations"]),
    default="relevance",
    show_default=True,
    help="relevance：依關鍵字相關度排序；citations：依全領域引用數排序，找最具影響力的論文。",
)
@click.option("--min-citations", default=0, show_default=True, help="過濾掉引用數低於此值的論文。")
@click.option("--year-from", default=None, type=int, help="只保留此年份（含）之後發表的論文。")
@click.option(
    "--translate",
    is_flag=True,
    default=False,
    help="先用 Haiku 把（中文）關鍵字翻成英文檢索詞再搜尋，提升英文語料庫的命中率；純英文關鍵字會自動略過、不額外花費。",
)
@click.option(
    "--output",
    "output_path",
    default=None,
    help="輸出的 markdown 檔案路徑（預設：<keyword>_report.md）。",
)
def main(
    keyword: str,
    limit: int,
    model: str,
    sort: str,
    min_citations: int,
    year_from: int | None,
    translate: bool,
    output_path: str | None,
):
    """搜尋 KEYWORD 相關論文，並用 Claude 產出研究分析報告。"""
    load_dotenv()

    query = keyword
    translated_from = None
    if translate:
        try:
            query = translate_to_english_query(keyword)
        except Exception as e:  # noqa: BLE001 — any failure should just fall back, not abort
            click.echo(f"翻譯失敗，改用原關鍵字搜尋：{e}", err=True)
            query = keyword
        if query != keyword:
            translated_from = keyword
            click.echo(f"已將「{keyword}」翻譯為英文檢索詞：{query}")

    click.echo(f"[1/3] 在 Semantic Scholar、OpenAlex 搜尋「{query}」...")
    try:
        result = search(
            query, limit=limit, sort=sort, min_citations=min_citations, year_from=year_from
        )
    except SearchError as e:
        click.echo(f"錯誤：{e}", err=True)
        sys.exit(1)

    suggestions: list[str] = []
    if len(result.papers) < SPARSE_RESULT_THRESHOLD:
        try:
            suggestions = suggest_keywords(keyword)
        except Exception:  # noqa: BLE001 — suggestions are a nice-to-have, never abort the run for them
            suggestions = []

    if not result.papers:
        click.echo("找不到含摘要的相關論文，請換個關鍵字試試。", err=True)
        if suggestions:
            click.echo("可以試試這些關鍵字：", err=True)
            for s in suggestions:
                click.echo(f"  - {s}", err=True)
        sys.exit(1)

    papers = result.papers
    source_note = ""
    if result.sources:
        source_note = "（" + "、".join(f"{n} {c} 篇" for n, c in result.sources.items()) + "）"
    click.echo(f"找到 {len(papers)} 篇含摘要的論文。{source_note}")
    if result.excluded_no_abstract:
        click.echo(f"（另有 {result.excluded_no_abstract} 篇命中但因無摘要未納入。）")
    if result.excluded_duplicates:
        click.echo(f"（已合併 {result.excluded_duplicates} 篇跨資料庫重複的論文。）")
    if result.failed_databases:
        click.echo(
            f"（注意：{'、'.join(result.failed_databases)} 查詢失敗，已改用其他來源。）", err=True
        )
    if suggestions:
        click.echo("論文數較少，若想擴大搜尋範圍可以試試：")
        for s in suggestions:
            click.echo(f"  - {s}")

    click.echo(f"[2/3] 使用 Claude ({model}) 分析論文...")
    try:
        analysis = analyze(keyword, papers, model=model)
    except RuntimeError as e:
        click.echo(f"錯誤：{e}", err=True)
        sys.exit(1)

    verification = verify_matrix(analysis, papers)
    if verification.checked and verification.unmatched_titles:
        click.echo(
            f"⚠️ 驗證：文獻矩陣有 {len(verification.unmatched_titles)} 列無法對應到實際檢索的論文，"
            "已在報告「檢索說明」標註，請覆核。",
            err=True,
        )
    elif verification.checked:
        click.echo(
            f"✅ 驗證：文獻矩陣 {verification.matched_rows}/{verification.total_rows} 列均對應到實際論文。"
        )

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
        verification=verification,
    )

    out_path = Path(output_path) if output_path else unique_report_path(Path.cwd(), keyword)
    click.echo(f"[3/3] 寫入報告到 {out_path}")
    out_path.write_text(report, encoding="utf-8")

    click.echo("完成！")


if __name__ == "__main__":
    main()
