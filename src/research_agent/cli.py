"""research-agent: search Semantic Scholar, analyze with Claude, write a markdown report."""

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from research_agent import cache
from research_agent.analyzer import DEFAULT_MODEL, analyze
from research_agent.citations import write_exports
from research_agent.claim_check import check_claims
from research_agent.fulltext import extract_fulltext_notes
from research_agent.query import (
    SPARSE_RESULT_THRESHOLD,
    suggest_academic_terms,
    suggest_keywords,
    translate_to_english_query,
)
from research_agent.relevance import filter_by_relevance
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
    "--translate/--no-translate",
    default=True,
    show_default=True,
    help="中文（非 ASCII）關鍵字預設會同時用原文與 Haiku 英譯詞「雙查」再合併，"
    "大幅提升英文語料庫的命中率；純英文關鍵字不受影響、不額外花費。--no-translate 只用原文查。",
)
@click.option(
    "--relevance-filter/--no-relevance-filter",
    default=True,
    show_default=True,
    help="送交分析前，先用 Haiku 為每篇論文打主題相關分、剔除明顯離題的論文，"
    "提升綜述的切題度；剔除情形會記在報告附錄。--no-relevance-filter 可關閉。",
)
@click.option(
    "--verify-claims/--no-verify-claims",
    default=True,
    show_default=True,
    help="（會額外花費，預設開）分析後再用 Haiku 逐列核對「主要發現」是否真有對應論文摘要支撐，"
    "揪出過度詮釋或失準的列——這是對引用傷害最大的失敗。每次多一次 Haiku 呼叫（已快取）；"
    "結果記在報告附錄。--no-verify-claims 可關閉。",
)
@click.option(
    "--fulltext/--no-fulltext",
    default=False,
    show_default=True,
    help="（會額外花費、需 pypdf）對開放取用論文（arXiv 直連／Unpaywall）抓取全文，"
    "用 Haiku 萃取作者自陳的「方法與限制」，突破只讀摘要的限制。僅 OA、上限數篇；"
    "預設關閉。需設 UNPAYWALL_EMAIL 或 OPENALEX_MAILTO 才會走 Unpaywall。",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="不使用快取。預設會把相同關鍵字＋參數的搜尋與分析結果快取在 "
    ".research_agent_cache/，讓重跑免費且即時。",
)
@click.option(
    "--suggest-terms",
    is_flag=True,
    default=False,
    help="不執行搜尋，只用 Haiku 列出 KEYWORD 可能對應的學術英文檢索詞（附中文說明），"
    "適合不熟悉領域術語時先參考、再挑一個重新執行。",
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
    relevance_filter: bool,
    verify_claims: bool,
    fulltext: bool,
    no_cache: bool,
    suggest_terms: bool,
    output_path: str | None,
):
    """搜尋 KEYWORD 相關論文，並用 Claude 產出研究分析報告。"""
    load_dotenv()
    if no_cache:
        cache.disable()

    if suggest_terms:
        try:
            terms = suggest_academic_terms(keyword)
        except Exception as e:  # noqa: BLE001 — report and exit, nothing else to fall back to
            click.echo(f"建議學術用語失敗：{e}", err=True)
            sys.exit(1)
        if not terms:
            click.echo("沒有取得建議用語。")
            return
        click.echo(f"「{keyword}」可能對應的學術檢索詞：")
        for t in terms:
            click.echo(f"  - {t.term}" + (f"    （{t.gloss}）" if t.gloss else ""))
        click.echo(f'\n可挑一個重新執行，例如：research-agent "{terms[0].term}"')
        return

    # Default-on for non-ASCII keywords: search the original *and* its English
    # translation ("dual-query") and merge, so a Chinese keyword no longer yields
    # the few-and-biased results an English-dominated corpus returns for it. A
    # plain-English keyword translates to itself, so this stays a single query.
    queries = [keyword]
    translated_from = None
    if translate:
        try:
            translated = translate_to_english_query(keyword)
        except Exception as e:  # noqa: BLE001 — any failure just falls back to the original
            click.echo(f"翻譯失敗，改用原關鍵字搜尋：{e}", err=True)
            translated = keyword
        if translated and translated != keyword:
            queries = [keyword, translated]
            translated_from = keyword
            click.echo(f"中文關鍵字：將同時用原文與英譯「雙查」→「{keyword}」＋「{translated}」")

    shown = " ＋ ".join(f"「{q}」" for q in queries)
    click.echo(f"[1/3] 在 Semantic Scholar、OpenAlex、arXiv 搜尋 {shown} ...")
    try:
        result = search(
            queries, limit=limit, sort=sort, min_citations=min_citations, year_from=year_from
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

    # Relevance gate: drop keyword-coincidence papers before the (paid) analysis,
    # so the review isn't written over a near-random off-topic sample.
    relevance = None
    if relevance_filter:
        relevance = filter_by_relevance(keyword, papers)
        if relevance.checked and relevance.dropped:
            click.echo(
                f"相關度過濾：剔除 {len(relevance.dropped)} 篇離題論文，保留 {len(relevance.kept)} 篇。"
            )
            for t in relevance.dropped_titles:
                click.echo(f"  - {t}")
        if relevance.checked:
            papers = relevance.kept
        if relevance.inconclusive:
            click.echo("⚠️ 所有論文相關度偏低，已保留全部、請謹慎解讀。", err=True)

    click.echo(f"[2/3] 使用 Claude ({model}) 分析 {len(papers)} 篇論文...")
    try:
        analysis = analyze(keyword, papers, model=model)
    except RuntimeError as e:
        click.echo(f"錯誤：{e}", err=True)
        sys.exit(1)

    verification = verify_matrix(analysis, papers)
    if verification.checked:
        issues = []
        if verification.unmatched_titles:
            issues.append(f"{len(verification.unmatched_titles)} 列無法對應實際論文")
        if verification.author_mismatches:
            issues.append(f"{len(verification.author_mismatches)} 列作者疑似張冠李戴")
        if verification.year_mismatches:
            issues.append(f"{len(verification.year_mismatches)} 列年份不符")
        if issues:
            click.echo(
                "⚠️ 驗證：文獻矩陣有 " + "、".join(issues) + "，已在報告「檢索說明」標註，請覆核。",
                err=True,
            )
        else:
            click.echo(
                f"✅ 驗證：文獻矩陣 {verification.matched_rows}/{verification.total_rows} "
                "列均對應實際論文，作者、年份與 metadata 一致。"
            )

    # Opt-in, paid: does each row's 主要發現 actually hold up against its abstract?
    claim_check = None
    if verify_claims:
        click.echo("內容支撐檢查：用 Haiku 逐列核對「主要發現」是否有摘要支撐...")
        claim_check = check_claims(analysis, papers)
        if claim_check.checked and claim_check.unsupported:
            click.echo(
                f"⚠️ 內容支撐：{len(claim_check.unsupported)}/{claim_check.total} 列「主要發現」"
                "摘要未明確支撐，已在報告「檢索說明」標註，請覆核。",
                err=True,
            )
        elif claim_check.checked:
            click.echo(f"✅ 內容支撐：{claim_check.total} 列「主要發現」皆有摘要支撐。")

    # Opt-in, paid: break the abstract-only ceiling for the OA subset by pulling
    # each open-access paper's full text and extracting its stated methods/limits.
    fulltext_notes = None
    if fulltext:
        click.echo("全文萃取：對開放取用論文抓取全文，萃取作者自陳的方法與限制...")
        fulltext_notes = extract_fulltext_notes(papers)
        if fulltext_notes.checked:
            click.echo(
                f"✅ 全文萃取：從 {len(fulltext_notes.notes)} 篇 OA 論文萃取方法/限制"
                f"（嘗試 {fulltext_notes.attempted} 篇）。"
            )
        else:
            click.echo("（全文萃取：沒有可用的 OA 全文或未能執行，略過。）")

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
        claim_check=claim_check,
        fulltext=fulltext_notes,
    )

    out_path = Path(output_path) if output_path else unique_report_path(Path.cwd(), keyword)
    click.echo(f"[3/3] 寫入報告到 {out_path}")
    out_path.write_text(report, encoding="utf-8")

    exports = write_exports(out_path, papers)
    if exports:
        click.echo(f"已輸出參考文獻匯出檔：{'、'.join(p.name for p in exports)}")

    click.echo("完成！")


if __name__ == "__main__":
    main()
