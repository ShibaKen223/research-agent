"""Assemble the final markdown report file."""

import re
from datetime import date
from pathlib import Path

from research_agent import citations

_SORT_LABELS = {
    "relevance": "關鍵字相關度",
    "citations": "全領域引用數（由高到低）",
}

# Shown in the header when no `stats` is available to read the real sources from.
_DEFAULT_SOURCES = ("Semantic Scholar", "OpenAlex", "arXiv")


def _source_label(stats) -> str:
    """The databases that actually contributed, read from `stats` — never a
    hardcoded single source (which used to wrongly say "Semantic Scholar" even
    when OpenAlex supplied papers)."""
    if stats is not None and getattr(stats, "databases", None):
        dbs = list(dict.fromkeys(stats.databases))
        if dbs:
            return "、".join(dbs)
    return "、".join(_DEFAULT_SOURCES)


# A references/參考文獻 heading and its body, up to the next heading or EOF.
_MODEL_REFS_RE = re.compile(
    r"^[ \t]*#{1,6}[ \t]*(?:參考文獻|references)[ \t]*$.*?(?=^[ \t]*#{1,6}[ \t]|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _strip_model_references(markdown: str) -> str:
    """Drop any references section the model wrote itself.

    The prompt tells the model not to, but a prompt is only a request. References
    must be program-generated from real metadata (zero hallucination), so any the
    model emits are removed before the authoritative `## 參考文獻` is appended —
    otherwise the report would carry two, the model's with transcribed (and
    sometimes wrong) DOIs."""
    return _MODEL_REFS_RE.sub("", markdown).rstrip()


# These two sections are pure LLM inference over the (small) abstract sample — they
# are NOT checked by verify.py / claim_check.py, which only validate the 文獻矩陣. A
# reader can too easily lift them as conclusions, so each is prefixed with an
# explicit caveat naming the sample size and the (uncovered) Chinese literature.
_UNVERIFIED_SECTIONS = ("研究缺口", "碩論題目建議")


def _unverified_note(paper_count: int) -> str:
    return (
        f"**⚠️ 注意：本段為 AI 在 {paper_count} 篇摘要上的歸納推論，未經程式驗證**"
        "（verify／claim_check 只核對「文獻矩陣」是否對應真實論文，不驗證此處推論）。"
        "樣本小、且未涵蓋華藝／臺灣碩博士論文網／CNKI 等中文文獻，"
        "請當作腦力激盪的起點，不可當作「領域事實」或「題目確定新穎」的定論——"
        "務必回到原始文獻、並另查上述中文資料庫後再下判斷。"
    )


def _annotate_unverified(markdown: str, paper_count: int) -> str:
    """Prefix each model-inference-only section with an explicit, un-missable caveat
    so neither the report nor the web view presents it as a verified conclusion."""
    note = _unverified_note(paper_count)
    for sec in _UNVERIFIED_SECTIONS:
        markdown = re.sub(
            rf"^(##[ \t]*{sec}[ \t]*)$",
            lambda m, n=note: f"{m.group(1)}\n\n{n}",
            markdown,
            count=1,
            flags=re.MULTILINE,
        )
    return markdown


def build_report(
    keyword: str,
    paper_count: int,
    analysis_markdown: str,
    *,
    queries: list[str] | None = None,
    translated_from: str | None = None,
    sort: str | None = None,
    min_citations: int = 0,
    year_from: int | None = None,
    model: str | None = None,
    stats=None,
    verification=None,
    papers: list[dict] | None = None,
    relevance=None,
    claim_check=None,
    fulltext=None,
    ndltd=None,
) -> str:
    """Assemble the final report.

    `papers`, if given, are the papers actually analysed; a `## 參考文獻` section
    with their full citations + DOI/links + a sibling `.bib`/`.ris` export is built
    straight from this metadata so the report can be cited without re-searching.

    When `queries` is given, a `## 檢索說明` appendix documents how the report was
    produced (databases, query/queries, filters, model) and how many papers were
    found vs. excluded — a reproducible, auditable search record. `stats` is the
    `SearchResult` (exclusion/dedup/source counts and the real source list, now
    also used for the header). `translated_from`, if set, is the original keyword a
    query was auto-translated from. `relevance`, if set, is the `RelevanceResult`
    from `relevance.filter_by_relevance`, disclosing how many off-topic papers were
    dropped. `verification`, if set, is the `VerificationResult` from
    `verify.verify_matrix`, stating whether every 文獻矩陣 row maps to a real paper
    (and now also whether each row's 作者/年份 match the metadata). `claim_check`, if
    set, is the opt-in `ClaimCheckResult` from `claim_check.check_claims`, disclosing
    which rows' 主要發現 the abstract doesn't support.
    """
    header = (
        f"# 研究分析報告：{keyword}\n\n"
        f"- 產生日期：{date.today().isoformat()}\n"
        f"- 分析論文數量：{paper_count}\n"
        f"- 資料來源：{_source_label(stats)}\n\n"
        "---\n\n"
    )
    body = (
        header
        + _annotate_unverified(_strip_model_references(analysis_markdown).strip(), paper_count)
        + "\n"
    )

    if papers:
        body += "\n" + citations.reference_list_markdown(papers)

    if ndltd is not None:
        body += "\n" + _thesis_section(ndltd)

    if queries:
        body += "\n" + _search_appendix(
            queries=queries,
            translated_from=translated_from,
            paper_count=paper_count,
            sort=sort,
            min_citations=min_citations,
            year_from=year_from,
            model=model,
            stats=stats,
            verification=verification,
            relevance=relevance,
            claim_check=claim_check,
            fulltext=fulltext,
        )
    return body


def _thesis_section(ndltd) -> str:
    """Render the program-built `## 臺灣碩博士論文對照` section from a
    `ndltd.ThesisCrossCheckResult` — existing Taiwan theses whose titles match the
    topic, for a novelty cross-check the abstract-based sources can't provide."""
    lines = ["## 臺灣碩博士論文對照", ""]
    lines.append(
        "以國家圖書館「臺灣博碩士論文知識加值系統」官方開放資料比對論文標題，"
        "列出與本主題相關的既有碩博士論文，供查證「題目是否已被做過」。"
        "**僅比對最近數個學年度、且僅依標題（此開放資料不含摘要），相關度由 Haiku 評分**——"
        "因此這是「有沒有人做過類似題目」的線索，不是內容層級的分析。"
    )
    lines.append("")
    if not ndltd.checked:
        lines += ["> ⚠️ 開放資料下載失敗，本次未能比對（不影響其他章節）。", ""]
        return "\n".join(lines)

    years = "、".join(str(y) for y in ndltd.years) or "—"
    lines.append(f"- 比對學年度（民國）：{years}")
    if ndltd.scored:
        lines.append(f"- 標題命中：{ndltd.matched} 筆；經 Haiku 相關評分後列出：{len(ndltd.theses)} 筆")
    else:
        lines.append(
            f"- 標題命中：{ndltd.matched} 筆；⚠️ 未能評分，以下為標題命中（可能含離題）：{len(ndltd.theses)} 筆"
        )
    lines.append("")

    if not ndltd.theses:
        lines += [
            "在比對的學年度內，未找到標題與本主題相關的碩博士論文。"
            "（注意：僅近數年、僅標題比對，並非「全無相關研究」的證明。）",
            "",
        ]
        return "\n".join(lines)

    for i, t in enumerate(ndltd.theses, 1):
        title = t.get("title") or "（無題名）"
        meta = "·".join(x for x in (t.get("school", ""), t.get("dept", "")) if x)
        yd = ((f"{t['year']} 學年度" if t.get("year") else "") + (f" {t['degree']}" if t.get("degree") else "")).strip()
        who = (t.get("author") or "") + (f"（指導：{t['advisor']}）" if t.get("advisor") else "")
        seg = "，".join(x for x in (meta, yd, who) if x)
        line = f"{i}. **{title}**"
        if t.get("title_en"):
            line += f"（{t['title_en']}）"
        if seg:
            line += f" — {seg}。"
        if t.get("url"):
            line += f" {t['url']}"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def _search_appendix(
    *, queries, translated_from, paper_count, sort, min_citations, year_from,
    model, stats, verification, relevance, claim_check, fulltext,
) -> str:
    """Render the `## 檢索說明` provenance section."""
    filters = []
    if year_from is not None:
        filters.append(f"{year_from} 年（含）後發表")
    if min_citations:
        filters.append(f"引用數 ≥ {min_citations}")
    filter_label = "、".join(filters) if filters else "無"

    if len(queries) > 1:
        extra = "、".join(f"`{q}`" for q in queries[1:])
        query_line = (
            f"- 檢索式：`{queries[0]}`（原文）＋ {extra}（自動英譯）—— 原文與英文雙查後合併"
        )
    elif translated_from:
        query_line = f"- 檢索式：`{queries[0]}`（由關鍵字「{translated_from}」自動翻譯為英文）"
    else:
        query_line = f"- 檢索式：`{queries[0]}`"

    db_label = _source_label(stats)

    lines = [
        "## 檢索說明",
        "",
        "本報告的文獻來源與檢索條件如下，供查證與重現。",
        "",
        "### 檢索條件",
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
        lines += ["", "### 檢索結果統計", ""]
        if stats.total_matches is not None:
            lines.append(f"- 各資料庫命中估計合計：約 {stats.total_matches}")
        lines += [
            f"- 實際取回筆數：{stats.fetched}",
            f"- 因缺少摘要而排除：{stats.excluded_no_abstract}",
            f"- 因不符篩選條件而排除：{stats.excluded_by_filter}",
        ]
        if stats.excluded_duplicates:
            lines.append(f"- 跨資料庫重複而合併：{stats.excluded_duplicates}")
        # When the relevance gate dropped papers, the final analysed count lives
        # in the relevance block below; here we report the pre-filter total so it
        # reconciles with the per-source contributions.
        search_included = sum(stats.sources.values()) if stats.sources else paper_count
        if relevance is not None and relevance.checked and relevance.dropped:
            lines.append(f"- 通過搜尋與跨來源去重：{search_included}")
        else:
            lines.append(f"- 最終納入分析：{paper_count}")
        if stats.sources:
            contrib = "、".join(f"{name} {count} 篇" for name, count in stats.sources.items())
            lines.append(f"- 各來源貢獻：{contrib}")
        if stats.failed_databases:
            failed = "、".join(stats.failed_databases)
            lines.append(f"- ⚠️ 查詢失敗、未納入的資料庫：{failed}")

    if relevance is not None:
        if relevance.checked:
            lines += [
                "",
                "### 相關度過濾",
                "",
                f"送交分析前由 {relevance.model} 為每篇評分、剔除離題論文。",
                "",
            ]
            lines.append(f"- 判定相關、納入分析：{len(relevance.kept)}")
            if relevance.dropped:
                lines.append(f"- 判定離題而剔除：{len(relevance.dropped)}")
                lines += [f"  - {t}" for t in relevance.dropped_titles]
            if relevance.inconclusive:
                lines.append(
                    "- ⚠️ 全部論文相關度偏低，已保留全部、未剔除；樣本可能離題，請謹慎解讀。"
                )
            elif not relevance.dropped:
                lines.append("- 所有論文皆判定與主題相關，未剔除。")
        else:
            lines += [
                "",
                "### 相關度過濾",
                "",
                "本次未能執行（缺金鑰或暫時失敗），已保留全部論文。",
                "",
            ]

    if verification is not None and verification.checked:
        lines += [
            "",
            "### 分析驗證",
            "",
            "程式自動核對矩陣，非模型自述。",
            "",
        ]
        lines.append(f"- 文獻矩陣列數：{verification.total_rows}")
        lines.append(f"- 可對應到實際檢索論文：{verification.matched_rows}")
        if verification.unmatched_titles:
            lines.append(
                f"- ⚠️ 無法對應、可能為杜撰的列（{len(verification.unmatched_titles)}）："
            )
            lines += [f"  - {title}" for title in verification.unmatched_titles]
        if verification.author_mismatches:
            lines.append(
                f"- ⚠️ 作者疑似張冠李戴、與資料庫 metadata 不符"
                f"（{len(verification.author_mismatches)}）："
            )
            lines += [
                f"  - 「{m.title}」標示作者「{m.claimed}」，實際應為 {m.actual}"
                for m in verification.author_mismatches
            ]
        if verification.year_mismatches:
            lines.append(
                f"- ⚠️ 年份與資料庫 metadata 不符（{len(verification.year_mismatches)}）："
            )
            lines += [
                f"  - 「{m.title}」標示 {m.claimed}，實際為 {m.actual}"
                for m in verification.year_mismatches
            ]
        if verification.ok:
            lines.append(
                "- ✅ 矩陣每一列都對應到實際檢索的論文，且作者、年份皆與資料庫 metadata 一致，"
                "未發現杜撰或張冠李戴。"
            )
        if verification.missing_papers:
            lines.append(f"- 已檢索但未列入矩陣的論文：{len(verification.missing_papers)}")

    if claim_check is not None and claim_check.checked:
        lines += [
            "",
            "### 內容支撐檢查",
            "",
            f"由 {claim_check.model} 逐列核對「主要發現」是否有對應摘要支撐。",
            "",
        ]
        lines.append(f"- 已檢查列數：{claim_check.total}")
        lines.append(f"- 摘要可支撐：{claim_check.supported}")
        if claim_check.unsupported:
            lines.append(
                f"- ⚠️ 摘要未明確支撐、可能過度詮釋或失準的列（{len(claim_check.unsupported)}）："
            )
            lines += [
                f"  - 「{it.title}」：{it.finding}" for it in claim_check.unsupported
            ]
        else:
            lines.append("- ✅ 每列主要發現皆可由對應論文摘要支撐。")

    if fulltext is not None and fulltext.checked:
        lines += [
            "",
            "### 全文限制與方法（OA 子集）",
            "",
            f"對開放取用論文抓取全文，由 {fulltext.model} 萃取作者自陳的方法與限制。"
            "僅涵蓋 OA 論文、且僅供參考——這不是方法品質評估，複雜版面也可能萃取不全。",
            "",
        ]
        lines.append(
            f"- 嘗試抓取全文：{fulltext.attempted} 篇；成功萃取：{len(fulltext.notes)} 篇"
        )
        for note in fulltext.notes:
            lines.append(f"- 「{note.title}」")
            if note.methods:
                lines.append(f"  - 方法：{note.methods}")
            if note.limitations:
                lines.append(f"  - 限制：{note.limitations}")

    lines += [
        "",
        "### 納入準則",
        "",
        "僅納入上述資料庫提供摘要（多為英文）的論文；"
        "分析內容僅依據各論文之標題與摘要，未取用全文。"
        "因此實際符合主題但無摘要、或未被這些資料庫收錄的論文可能未納入，"
        "解讀時請留意此覆蓋範圍限制。",
        "",
        "⚠️ **中文文獻覆蓋限制：** 本工具來源為 Semantic Scholar／OpenAlex／arXiv，"
        "**未涵蓋華藝（airiti）、臺灣碩博士論文網、CNKI、TCI** 等中文／臺灣資料庫。"
        "因此「研究缺口」與「碩論題目建議」可能漏看既有的中文研究與碩博士論文；"
        "判斷題目是否新穎時，請務必另行查證這些資料庫。",
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
