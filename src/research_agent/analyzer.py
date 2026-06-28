"""Send the collected papers to Claude and get back a markdown analysis."""

import json
import os

import anthropic

from research_agent import cache

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192

PROMPT_TEMPLATE = """\
你是一位學術研究助理，請根據以下關於「{keyword}」的論文清單，撰寫一份繁體中文的研究分析報告（Markdown 格式）。

重要規則（攸關報告的學術可信度，務必嚴格遵守）：
- 你只能依據下方清單提供的論文標題與摘要進行分析，不得使用清單以外的任何知識或記憶，也不得引用清單中沒有的論文。
- 若某篇論文的摘要未提供某項資訊（例如研究方法、樣本、數據），對應欄位請填「摘要未說明」，不要自行推測或補充。
- 文獻矩陣中的每一列都必須真實對應清單中的某一篇論文，不得新增、合併或虛構論文。
- 分析（趨勢、缺口、題目建議）只能建立在這些摘要實際呈現的內容上；若證據不足，請明說「現有摘要證據有限」，不要過度推論。

報告必須包含以下四個章節，標題請完全使用這些文字：

## 文獻矩陣
用表格列出每篇論文的：標題、作者（第一作者即可）、年份、期刊/會議、引用數、研究方法/主題、主要發現。
「期刊/會議」直接照抄清單中該論文的 venue 欄；若清單未提供（venue 為空）則填「未提供」。
（DOI 與連結不必放進表格，報告會另附「參考文獻」章節由程式精確列出，避免抄錯。）

## 研究趨勢
分析這些論文反映出的研究趨勢與演進方向（3-6 點）。每一點都必須用 `### ` 三級標題開頭（例如 `### 1. 標題文字`），標題單獨一行、不要加粗星號，內文另起一段。

## 研究缺口
指出目前文獻中尚未被充分探討、或互相矛盾的問題（3-6 點）。格式規則與「研究趨勢」相同：每一點都用 `### ` 三級標題開頭。

## 碩論題目建議
根據上述缺口，提出 3-5 個具體可行的碩士論文題目，每個題目附一句話說明其研究價值。每個題目都必須用 `### ` 三級標題開頭（例如 `### 題目一`），標題下一行用粗體寫出論文題目，再下一行用 `> ` 引言格式說明研究價值。

以下是論文清單（JSON）：

{papers_json}
"""


def analyze(keyword: str, papers: list[dict], model: str = DEFAULT_MODEL) -> str:
    papers_json = _papers_to_json(papers)
    prompt = PROMPT_TEMPLATE.format(keyword=keyword, papers_json=papers_json)

    # temperature=0 makes this deterministic, so an identical prompt always yields
    # an identical report: a cache hit is correct and lets a re-run skip the (paid,
    # Sonnet-level) call entirely — no API key even required to re-read it.
    ck = cache.key("analysis", model, prompt)
    hit = cache.get("analysis", ck)
    if hit is not None:
        return hit

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Put it in a .env file or export it as an env var."
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        temperature=0,  # deterministic: same papers -> same report, so results are reproducible
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    cache.set("analysis", ck, text)
    return text


# Only the fields the prompt/矩陣 actually use. Internal fields added for
# de-duplication and verification (doi, source, paper_id) are deliberately left
# out so they can't leak into the matrix or inflate the token count.
_PROMPT_FIELDS = ("title", "authors", "year", "abstract", "url", "venue", "citation_count")


def _papers_to_json(papers: list[dict]) -> str:
    slim = [{k: p.get(k) for k in _PROMPT_FIELDS} for p in papers]
    return json.dumps(slim, ensure_ascii=False, indent=2)
