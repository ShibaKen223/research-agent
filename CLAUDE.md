# research-agent

CLI 工具：輸入研究關鍵字 → 用 Semantic Scholar API 搜尋相關論文 → 用 Claude API 分析 → 產出 markdown 研究報告。

## 架構

```
src/research_agent/
  cli.py              CLI 入口（click），整合搜尋 → 分析 → 寫檔流程
  semantic_scholar.py 呼叫 Semantic Scholar Graph API（無需 API key），回傳 SearchResult（含摘要的論文清單＋命中/排除統計）
  query.py             （可選）用 Haiku 把中文關鍵字翻成英文檢索詞再搜尋；純英文關鍵字會自動略過、不呼叫 API
  analyzer.py          將論文清單組成 prompt 送給 Claude API（temperature=0、要求只依摘要分析），回傳 markdown 分析內容
  report.py            把分析內容加上 header（日期、論文數、來源），並在末尾附上「檢索說明」附錄（檢索式/篩選/統計），組成最終報告
  report_parser.py     共用的報告解析工具（parse_report/parse_markdown_table/year_distribution），api.py 依賴此模組
  api.py               FastAPI 後端，包成 HTTP API（搜尋/分析/報告 CRUD）給 web/ 前端呼叫，job 狀態存在記憶體
  api_cli.py            `research-agent-api` 的入口，單獨啟動 FastAPI 後端（uvicorn）
  view_cli.py           `research-agent-view` 的入口，同時啟動 FastAPI 後端與 web/（Next.js）前端的 dev server，並開啟瀏覽器
web/                  Next.js 網頁檢視器（取代舊版 Streamlit viewer），呼叫 api.py 的 HTTP API
```

資料流：（可選 `translate_to_english_query()`）-> `search_papers()` -> `analyze()` -> `build_report()` -> 寫入 `<keyword>_report.md`。

## 環境設定

- 需要 `ANTHROPIC_API_KEY`，放在專案根目錄的 `.env`（參考 `.env.example`），由 `python-dotenv` 載入。
- Semantic Scholar API 不需要 key，但有 rate limit；遇到 429 會拋出 `SemanticScholarError`。

## 安裝與執行

```bash
pip install -e .
research-agent "你的研究關鍵字" --limit 20 --output report.md
```

## 報告檢視器（GUI）

```bash
pip install -e ".[view]"
cd web && npm install && cd ..   # 第一次使用要先安裝前端依賴
research-agent-view
```

`research-agent-view` 會同時啟動 FastAPI 後端（:8000）與 Next.js 前端（:3000），並自動開啟瀏覽器到 `http://localhost:3000`。前端透過 `web/lib/api.ts` 呼叫後端的 `/api/reports`、`/api/search`、`/api/jobs/{id}` 等端點，後端用 `report_parser.parse_report()` 掃描當前目錄下的 `*_report.md` 與 `reports/*.md`，依「文獻矩陣／研究趨勢／研究缺口／碩論題目建議」四個固定章節分頁顯示（用 `## 標題` 切章節，章節標題改了要同步更新 `report_parser.SECTION_ORDER`）。Ctrl+C 會同時關閉前後端。

## 報告格式

Claude 產出的報告固定包含四個章節（章節標題為中文，分析時依賴這些固定標題）：
- 文獻矩陣
- 研究趨勢
- 研究缺口
- 碩論題目建議

若要調整報告結構，修改 `analyzer.py` 的 `PROMPT_TEMPLATE`。

除了上述四個 Claude 產出的章節，`report.py` 的 `build_report()` 還會在報告末尾自動附加一個 `## 檢索說明` 章節（非 Claude 產出，記錄檢索式、篩選條件、命中/排除統計、分析模型與納入準則，供查證與重現）。它不在 `report_parser.SECTION_ORDER` 內，前端會把它排在四個固定章節之後當作額外分頁顯示。

## 慣例

- 預設 model 是 `claude-sonnet-4-6`（定義於 `analyzer.DEFAULT_MODEL`），可用 `--model` 覆蓋。
- 只分析有摘要（abstract）的論文，沒有摘要的論文會在 `semantic_scholar.search_papers()` 被過濾掉（但會計入 `SearchResult` 的排除統計，並在報告的「檢索說明」附錄回報排除了幾篇）。
- 關鍵字翻譯（CLI `--translate`、web 搜尋列開關）預設**關閉**。打開時才會用 `query.TRANSLATE_MODEL`（Haiku，刻意用便宜模型）多呼叫一次 Claude；純英文關鍵字（`keyword.isascii()`）會自動略過、不花費。翻譯失敗會退回原關鍵字、不中斷搜尋。報告標題仍用原關鍵字，「檢索說明」附錄會記錄實際送出的英文檢索式並註明是翻譯來的。
- 不要把 `.env` 或產出的報告（`reports/`、`*_report.md`）commit 進版本控制。
