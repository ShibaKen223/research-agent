# research-agent

CLI 工具：輸入研究關鍵字 → 用 Semantic Scholar＋OpenAlex 搜尋相關論文（多來源、去重；中文關鍵字預設原文＋英譯雙查）→ 用 Haiku 剔除離題論文 → 用 Claude 分析 → 程式自動驗證 → 產出附參考文獻的 markdown 研究報告。

## 架構

```
src/research_agent/
  cli.py              CLI 入口（click），整合搜尋 → 分析 → 驗證 → 寫檔流程
  sources.py          多來源協調器：同時查 Semantic Scholar＋OpenAlex，依 DOI／標題去重、合併排序，回傳合併後的 SearchResult；單一來源失敗會降級用其他來源
  semantic_scholar.py 呼叫 Semantic Scholar Graph API（無需 key），回傳 SearchResult（論文清單＋命中/排除/去重/來源統計）；也定義 SearchResult dataclass
  openalex.py         呼叫 OpenAlex API（無需 key，~2.5 億筆），把 abstract_inverted_index 還原成摘要；輸出與 semantic_scholar 相同的 SearchResult 形狀
  relevance.py        相關度關卡：送交分析前用 Haiku 一次批次為每篇論文打主題相關分（0–3），剔除明顯離題（關鍵字巧合）的論文。**fail-open**：任何錯誤、無法解析、或「全部都判離題」都改成保留全部（標記 inconclusive），永遠不會清空或中斷一次搜尋。回傳 RelevanceResult，剔除情形揭露在報告附錄
  verify.py           反幻覺關卡（純程式、不花 API）：解析「文獻矩陣」每一列，(1) 比對是否真的對應到送進模型的論文（正規化＋difflib 模糊比對）；(2) 對已對應的列再**內容核對** metadata——「作者」必須與該論文實際作者有共同姓名 token（否則標為**張冠李戴**），「年份」與實際年份衝突則標記（皆刻意保守，只在零重疊／明確衝突時才報，避免誤殺）。回傳 VerificationResult（含 author_mismatches／year_mismatches）
  claim_check.py      內容支撐檢查（**opt-in、會花費**，預設關閉）：分析後用 Haiku 一次批次，逐列核對「主要發現」是否真有對應論文摘要支撐（0–2 分，只報 0＝摘要不支撐）。揪出 verify.py 抓不到的「過度詮釋／杜撰結論」。**fail-open**＋快取，與 relevance.py 同形狀（`_parse_scores`／`_coerce_int_keys` 是 relevance 的雙生，改一個要同步）。CLI `--verify-claims`、API `verify_claims`
  citations.py        從**實際論文 metadata**（非模型產出）產生「## 參考文獻」章節與 BibTeX／RIS 匯出（`write_exports()` 寫出 `<report>.bib`/`.ris`）；DOI/連結/venue 直接取自 metadata，零幻覺風險。刻意不把 DOI 放進 Claude 寫的矩陣，避免模型抄錯
  cache.py            on-disk JSON 快取（`.research_agent_cache/`，可用 `RESEARCH_AGENT_CACHE_DIR` 覆寫）：依輸入對「搜尋／Haiku 相關度／Sonnet 分析」各自快取，重跑同關鍵字免費又即時。`--no-cache` 或 `RESEARCH_AGENT_NO_CACHE=1` 關閉
  text_utils.py       共用的 normalize_doi／normalize_title（去重與驗證共用，獨立模組避免循環 import）
  query.py             用 Haiku 把中文關鍵字翻成英文檢索詞（供雙查用）；純英文關鍵字會自動略過、不呼叫 API。也提供 `suggest_academic_terms()`：使用者不熟領域術語時，主動建議學術界慣用的英文檢索詞（非直譯）
  analyzer.py          將論文清單組成 prompt 送給 Claude API（temperature=0、要求只依摘要分析），回傳 markdown 分析內容；依 prompt 對結果做快取
  report.py            把分析內容加上 header（資料來源讀自 `stats`，非寫死），附上程式產生的「## 參考文獻」與「## 檢索說明」附錄（檢索式/篩選/多來源統計/相關度過濾/分析驗證），組成最終報告
  report_parser.py     共用的報告解析工具（parse_report/parse_markdown_table/year_distribution），api.py 與 verify.py 依賴此模組
  api.py               FastAPI 後端，包成 HTTP API（搜尋/分析/報告 CRUD）給 web/ 前端呼叫，job 狀態存在記憶體
  api_cli.py            `research-agent-api` 的入口，單獨啟動 FastAPI 後端（uvicorn）
  view_cli.py           `research-agent-view` 的入口，同時啟動 FastAPI 後端與 web/（Next.js）前端的 dev server，並開啟瀏覽器
web/                  Next.js 網頁檢視器（取代舊版 Streamlit viewer），呼叫 api.py 的 HTTP API
```

資料流：（非 ASCII 關鍵字預設先 `translate_to_english_query()` 得英譯詞）→ `sources.search([原文, 英譯])`（多來源＋雙查、去重）→ `filter_by_relevance()`（Haiku 剔除離題）→ `analyze()` → `verify_matrix()`（存在性＋作者/年份內容核對）→（`--verify-claims` 時）`check_claims()`（Haiku 核對主要發現是否有摘要支撐）→ `build_report()`（含程式產生的參考文獻）→ 寫入 `<keyword>_report.md`，並 `write_exports()` 寫出 `.bib`/`.ris`。搜尋／相關度／分析／內容支撐檢查都會經 `cache.py` 快取。

## 環境設定

- 需要 `ANTHROPIC_API_KEY`，放在專案根目錄的 `.env`（參考 `.env.example`），由 `python-dotenv` 載入。
- Semantic Scholar 與 OpenAlex API 都不需要 key，但都有 rate limit；遇到 429 會各自重試（honor Retry-After），重試到頂才拋錯。
- （可選）設 `OPENALEX_MAILTO=你的email` 可進入 OpenAlex 較快的 polite pool；不設也能用。不要把個人 email 寫死進程式碼。
- 預設會把搜尋／相關度／分析結果快取在工作目錄的 `.research_agent_cache/`（已列入 `.gitignore`），同關鍵字＋參數重跑免費又即時；`--no-cache` 或 `RESEARCH_AGENT_NO_CACHE=1` 可關閉，`RESEARCH_AGENT_CACHE_DIR` 可換位置。離線單元測試（`tests/`）會在 import 時 `cache.disable()`，不碰磁碟。

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

除了上述四個 Claude 產出的章節，`report.py` 的 `build_report()` 還會在報告末尾自動附加兩個**非 Claude 產出**的章節（都不在 `report_parser.SECTION_ORDER` 內，前端會排在四個固定章節之後當額外分頁）：

- `## 參考文獻`：由 `citations.reference_list_markdown()` 直接從實際論文 metadata 產生的編號參考清單（作者/年份/標題/venue/DOI 或連結），可直接引用；另寫出 `<report>.bib`/`.ris` 供匯入文獻管理軟體。因為不是模型產出，零幻覺風險。
- `## 檢索說明`：記錄檢索式（雙查會列出原文＋英譯）、使用的資料庫、篩選條件、命中/排除/跨來源去重統計、各來源貢獻、**相關度過濾**（剔除幾篇離題、列出剔除標題；若全部偏低會標 inconclusive 警告）、分析模型、納入準則，以及一段「分析驗證」——由 `verify.verify_matrix()` 程式核對「文獻矩陣」每一列是否對應到實際檢索到的論文、且作者/年份是否與 metadata 一致，列出無法對應（疑似杜撰）、作者張冠李戴、年份不符的列。若開了 `--verify-claims`，還會多一段「內容支撐檢查」列出摘要未支撐的「主要發現」。供查證與重現。

## 慣例

- 預設 model 是 `claude-sonnet-4-6`（定義於 `analyzer.DEFAULT_MODEL`），可用 `--model` 覆蓋。
- 搜尋預設**同時查 Semantic Scholar 與 OpenAlex**（`sources.DEFAULT_DATABASES`），結果依 DOI（缺 DOI 時退回正規化標題）去重後合併；relevance 用 round-robin 交錯兩來源排名，citations 則合併後依引用數重排。任一來源失敗不會中斷整體搜尋，會記到 `SearchResult.failed_databases` 並在報告揭露。新增/移除來源改 `sources._SOURCES`；新來源的 `_normalize()` 必須輸出和既有來源相同的 dict 形狀（含 `doi`/`source`/`paper_id`）。
- 只分析有摘要（abstract）的論文，沒有摘要的論文會在各來源被過濾掉（但會計入 `SearchResult` 的排除統計，並在報告的「檢索說明」附錄回報排除了幾篇）。
- analyzer 的 prompt grounding 只是「要求」，`verify.verify_matrix()` 是「事後查核」（純程式、不花 API）：用標題正規化＋difflib 比對，確認「文獻矩陣」每列都對得上實際論文；對上之後再**內容核對** metadata——作者必須與該論文真實作者有共同姓名 token（零重疊＝張冠李戴）、年份不得與實際年份衝突。對不上／張冠李戴／年份不符的列都會在 CLI 印警告、並在報告「檢索說明」的「分析驗證」標註。比對依賴矩陣標題欄為「標題」、作者欄含「作者」、年份欄含「年」、章節標題為「文獻矩陣」（與 `analyzer.PROMPT_TEMPLATE` 綁定）。作者比對刻意保守（只比 Latin token、只在零重疊時報），避免把「列第二作者」「只寫姓」當成錯誤。
- **內容支撐檢查**（CLI `--verify-claims`、API `verify_claims`）預設**關閉**（會花費）：分析後 `claim_check.check_claims()` 用 Haiku 一次批次，把每列「主要發現」與該論文真實摘要逐一比對、評 0–2 分，只報 0（摘要不支撐）的列。這補上 `verify.py` 抓不到的「過度詮釋／杜撰結論」——verify 只證明論文存在且作者/年份對，不證明結論為真。**fail-open**＋快取（與 `relevance.py` 同形狀，`_parse_scores`/`_coerce_int_keys` 是雙生，改一個要同步另一個）。因為每跑必多一次 API，故依「API 預算吃緊」原則設為 opt-in。
- 關鍵字翻譯／**雙查**（CLI `--translate/--no-translate`、API `SearchRequest.translate`）預設**開啟**。對非 ASCII（中文）關鍵字，會用 `query.TRANSLATE_MODEL`（Haiku，便宜模型）多呼叫一次 Claude 取得英譯詞，然後**同時用原文與英譯兩條 query 搜尋再合併去重**（`sources.search()` 接受 `str | Sequence[str]`），大幅改善英文語料庫對中文關鍵字「又少又偏」的問題。純英文關鍵字（`keyword.isascii()`）翻成自己、等同單查、不花費。翻譯失敗會退回原關鍵字、不中斷搜尋。報告標題仍用原關鍵字，「檢索說明」附錄會列出兩條檢索式並註明雙查。`--no-translate` 只用原文查。
- **相關度過濾**（CLI `--relevance-filter/--no-relevance-filter`、API `relevance_filter`）預設**開啟**：搜尋後、送 Sonnet 分析前，`relevance.filter_by_relevance()` 用 Haiku 一次批次為每篇打 0–3 主題相關分，剔除 < `KEEP_THRESHOLD`（離題）的論文。這是針對「關鍵字巧合撈進無關論文、再被寫成漂亮綜述」的核心防線（`verify.py` 只驗論文存在、不驗切題）。**fail-open**：缺金鑰／API 失敗／無法解析／會把全部剔光時，一律保留全部（不中斷），剔除情形與「全部偏低」警告都揭露在「檢索說明」。它會減少送進 Sonnet 的論文數（順帶省分析成本）。
- **參考文獻與匯出**由 `citations.py` 在 `build_report()`／寫檔後用**程式**從實際 metadata 產生（`## 參考文獻` 章節＋ `<report>.bib`/`.ris`），不經模型，零幻覺。矩陣刻意不放 DOI（避免模型抄錯）；venue 是低風險顯示欄，由 prompt 要求模型照抄清單中的 `venue`。
- **快取**（`cache.py`）預設開：搜尋（依 queries＋參數）、相關度、分析（依完整 prompt，因 temperature=0 故同輸入同輸出）、內容支撐檢查各自快取在 `.research_agent_cache/`。命中分析快取連 API key 都不需要。`--no-cache`／`RESEARCH_AGENT_NO_CACHE=1` 關閉；改 prompt 想讓舊快取失效就 bump `cache.VERSION`。**注意**：相關度與內容支撐檢查的分數以 JSON 快取，key 會變字串，讀回時務必用 `_coerce_int_keys()` 轉回整數（否則全部 lookup miss → 形同沒過濾，這個 bug 已發生過）。
- 學術用語建議（CLI `--suggest-terms`、web 搜尋列「學術用語建議」按鈕）是完全獨立、使用者主動觸發的功能，不影響任何預設搜尋流程：呼叫 `query.suggest_academic_terms()`（同樣用 Haiku），回傳數個學術英文檢索詞＋一句中文說明。CLI 模式下只印出建議、不執行搜尋；web 點選建議詞只會把它填入搜尋框（不會自動送出搜尋），避免在使用者還在比較用詞時就誤觸發昂貴的 Sonnet 分析。與 `translate_to_english_query()` 不同，這個功能不是直譯、且不論關鍵字是否為 ASCII 都會呼叫 API（因為目的是換成更精確的學術用詞，不是翻譯）。
- 不要把 `.env`、產出的報告（`reports/`、`*_report.md`）、參考文獻匯出（`*_report.bib`/`.ris`）或快取（`.research_agent_cache/`）commit 進版本控制（皆已列入 `.gitignore`）。
