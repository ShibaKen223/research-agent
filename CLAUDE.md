# research-agent

CLI 工具：輸入研究關鍵字 → 用 Semantic Scholar＋OpenAlex 搜尋相關論文（多來源、去重）→ 用 Claude API 分析 → 程式自動驗證 → 產出 markdown 研究報告。

## 架構

```
src/research_agent/
  cli.py              CLI 入口（click），整合搜尋 → 分析 → 驗證 → 寫檔流程
  sources.py          多來源協調器：同時查 Semantic Scholar＋OpenAlex，依 DOI／標題去重、合併排序，回傳合併後的 SearchResult；單一來源失敗會降級用其他來源
  semantic_scholar.py 呼叫 Semantic Scholar Graph API（無需 key），回傳 SearchResult（論文清單＋命中/排除/去重/來源統計）；也定義 SearchResult dataclass
  openalex.py         呼叫 OpenAlex API（無需 key，~2.5 億筆），把 abstract_inverted_index 還原成摘要；輸出與 semantic_scholar 相同的 SearchResult 形狀
  verify.py           反幻覺關卡：解析「文獻矩陣」每一列，比對是否真的對應到送進模型的論文（正規化＋difflib 模糊比對），回傳 VerificationResult
  text_utils.py       共用的 normalize_doi／normalize_title（去重與驗證共用，獨立模組避免循環 import）
  query.py             （可選）用 Haiku 把中文關鍵字翻成英文檢索詞再搜尋；純英文關鍵字會自動略過、不呼叫 API。也提供 `suggest_academic_terms()`：使用者不熟領域術語時，主動建議學術界慣用的英文檢索詞（非直譯）
  analyzer.py          將論文清單組成 prompt 送給 Claude API（temperature=0、要求只依摘要分析），回傳 markdown 分析內容
  report.py            把分析內容加上 header，並在末尾附上「檢索說明」附錄（檢索式/篩選/多來源統計/分析驗證），組成最終報告
  report_parser.py     共用的報告解析工具（parse_report/parse_markdown_table/year_distribution），api.py 與 verify.py 依賴此模組
  api.py               FastAPI 後端，包成 HTTP API（搜尋/分析/報告 CRUD）給 web/ 前端呼叫，job 狀態存在記憶體
  api_cli.py            `research-agent-api` 的入口，單獨啟動 FastAPI 後端（uvicorn）
  view_cli.py           `research-agent-view` 的入口，同時啟動 FastAPI 後端與 web/（Next.js）前端的 dev server，並開啟瀏覽器
web/                  Next.js 網頁檢視器（取代舊版 Streamlit viewer），呼叫 api.py 的 HTTP API
```

資料流：（可選 `translate_to_english_query()`）-> `sources.search()`（多來源去重）-> `analyze()` -> `verify_matrix()` -> `build_report()` -> 寫入 `<keyword>_report.md`。

## 環境設定

- 需要 `ANTHROPIC_API_KEY`，放在專案根目錄的 `.env`（參考 `.env.example`），由 `python-dotenv` 載入。
- Semantic Scholar 與 OpenAlex API 都不需要 key，但都有 rate limit；遇到 429 會各自重試（honor Retry-After），重試到頂才拋錯。
- （可選）設 `OPENALEX_MAILTO=你的email` 可進入 OpenAlex 較快的 polite pool；不設也能用。不要把個人 email 寫死進程式碼。

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

`research-agent-view` 會同時啟動 FastAPI 後端（:8000，綁 `0.0.0.0`）與 Next.js 前端（:3000），並自動開啟瀏覽器到 `http://localhost:3000`。前端透過 `web/lib/api.ts` 呼叫後端的 `/api/reports`、`/api/search`、`/api/jobs/{id}` 等端點，後端用 `report_parser.parse_report()` 掃描當前目錄下的 `*_report.md` 與 `reports/*.md`，依「文獻矩陣／研究趨勢／研究缺口／碩論題目建議」四個固定章節分頁顯示（用 `## 標題` 切章節，章節標題改了要同步更新 `report_parser.SECTION_ORDER`）。Ctrl+C 會同時關閉前後端。

因為後端綁 `0.0.0.0`，同一個 Wi-Fi 下的其他裝置（手機等）可以用終端機印出的區網網址（`http://<區網IP>:3000`）連進來；`view_cli.py` 每次啟動會產生一個隨機 `RESEARCH_AGENT_TOKEN`，透過 `NEXT_PUBLIC_API_TOKEN` 烤進前端，後端 `api.py` 的 `require_token` middleware 會擋掉沒帶對 token 的 `/api/*` 請求（header `X-API-Token` 或下載連結用的 `?token=` query param），避免同網路的人亂打 `/api/search` 消耗 Claude API 額度。單獨用 `research-agent-api`／本機 `npm run dev`（沒設這個 token）時則完全不受影響，行為跟以前一樣。

## 報告格式

Claude 產出的報告固定包含四個章節（章節標題為中文，分析時依賴這些固定標題）：
- 文獻矩陣
- 研究趨勢
- 研究缺口
- 碩論題目建議

若要調整報告結構，修改 `analyzer.py` 的 `PROMPT_TEMPLATE`。

除了上述四個 Claude 產出的章節，`report.py` 的 `build_report()` 還會在報告末尾自動附加一個 `## 檢索說明` 章節（非 Claude 產出，記錄檢索式、使用的資料庫、篩選條件、命中/排除/跨來源去重統計、各來源貢獻、分析模型、納入準則，以及一段「分析驗證」——由 `verify.verify_matrix()` 程式核對「文獻矩陣」每一列是否對應到實際檢索到的論文，列出無法對應（疑似杜撰）的列），供查證與重現。它不在 `report_parser.SECTION_ORDER` 內，前端會把它排在四個固定章節之後當作額外分頁顯示。

## 慣例

- 預設 model 是 `claude-sonnet-4-6`（定義於 `analyzer.DEFAULT_MODEL`），可用 `--model` 覆蓋。
- 搜尋預設**同時查 Semantic Scholar 與 OpenAlex**（`sources.DEFAULT_DATABASES`），結果依 DOI（缺 DOI 時退回正規化標題）去重後合併；relevance 用 round-robin 交錯兩來源排名，citations 則合併後依引用數重排。任一來源失敗不會中斷整體搜尋，會記到 `SearchResult.failed_databases` 並在報告揭露。新增/移除來源改 `sources._SOURCES`；新來源的 `_normalize()` 必須輸出和既有來源相同的 dict 形狀（含 `doi`/`source`/`paper_id`）。
- 只分析有摘要（abstract）的論文，沒有摘要的論文會在各來源被過濾掉（但會計入 `SearchResult` 的排除統計，並在報告的「檢索說明」附錄回報排除了幾篇）。
- analyzer 的 prompt grounding 只是「要求」，`verify.verify_matrix()` 是「事後查核」：用標題正規化＋difflib 比對，確認「文獻矩陣」每列都對得上實際論文；對不上的列會在 CLI 印警告、並在報告「檢索說明」的「分析驗證」標註。比對依賴矩陣第一欄標題為「標題」、章節標題為「文獻矩陣」（與 `analyzer.PROMPT_TEMPLATE` 綁定）。
- 關鍵字翻譯（CLI `--translate`、web 搜尋列開關）預設**關閉**。打開時才會用 `query.TRANSLATE_MODEL`（Haiku，刻意用便宜模型）多呼叫一次 Claude；純英文關鍵字（`keyword.isascii()`）會自動略過、不花費。翻譯失敗會退回原關鍵字、不中斷搜尋。報告標題仍用原關鍵字，「檢索說明」附錄會記錄實際送出的英文檢索式並註明是翻譯來的。
- 學術用語建議（CLI `--suggest-terms`、web 搜尋列「學術用語建議」按鈕）是完全獨立、使用者主動觸發的功能，不影響任何預設搜尋流程：呼叫 `query.suggest_academic_terms()`（同樣用 Haiku），回傳數個學術英文檢索詞＋一句中文說明。CLI 模式下只印出建議、不執行搜尋；web 點選建議詞只會把它填入搜尋框（不會自動送出搜尋），避免在使用者還在比較用詞時就誤觸發昂貴的 Sonnet 分析。與 `translate_to_english_query()` 不同，這個功能不是直譯、且不論關鍵字是否為 ASCII 都會呼叫 API（因為目的是換成更精確的學術用詞，不是翻譯）。
- 不要把 `.env` 或產出的報告（`reports/`、`*_report.md`）commit 進版本控制。
