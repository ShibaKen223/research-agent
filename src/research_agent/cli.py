"""research-agent: search Semantic Scholar, analyze with Claude, write a markdown report."""

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from research_agent.analyzer import DEFAULT_MODEL, analyze
from research_agent.report import build_report
from research_agent.semantic_scholar import SemanticScholarError, search_papers


@click.command()
@click.argument("keyword")
@click.option("--limit", default=20, show_default=True, help="要搜尋的論文數量上限。")
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="使用的 Claude model。")
@click.option(
    "--output",
    "output_path",
    default=None,
    help="輸出的 markdown 檔案路徑（預設：<keyword>_report.md）。",
)
def main(keyword: str, limit: int, model: str, output_path: str | None):
    """搜尋 KEYWORD 相關論文，並用 Claude 產出研究分析報告。"""
    load_dotenv()

    click.echo(f"[1/3] 在 Semantic Scholar 搜尋「{keyword}」...")
    try:
        papers = search_papers(keyword, limit=limit)
    except SemanticScholarError as e:
        click.echo(f"錯誤：{e}", err=True)
        sys.exit(1)

    if not papers:
        click.echo("找不到含摘要的相關論文，請換個關鍵字試試。", err=True)
        sys.exit(1)

    click.echo(f"找到 {len(papers)} 篇含摘要的論文。")

    click.echo(f"[2/3] 使用 Claude ({model}) 分析論文...")
    try:
        analysis = analyze(keyword, papers, model=model)
    except RuntimeError as e:
        click.echo(f"錯誤：{e}", err=True)
        sys.exit(1)

    report = build_report(keyword, len(papers), analysis)

    out_path = Path(output_path) if output_path else Path(f"{keyword}_report.md")
    click.echo(f"[3/3] 寫入報告到 {out_path}")
    out_path.write_text(report, encoding="utf-8")

    click.echo("完成！")


if __name__ == "__main__":
    main()
