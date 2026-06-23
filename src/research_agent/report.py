"""Assemble the final markdown report file."""

from datetime import date


def build_report(keyword: str, paper_count: int, analysis_markdown: str) -> str:
    header = (
        f"# 研究分析報告：{keyword}\n\n"
        f"- 產生日期：{date.today().isoformat()}\n"
        f"- 分析論文數量：{paper_count}\n"
        f"- 資料來源：Semantic Scholar\n\n"
        "---\n\n"
    )
    return header + analysis_markdown.strip() + "\n"
