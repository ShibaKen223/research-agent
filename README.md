# research-agent 使用說明

CLI 工具：輸入研究關鍵字 → 用 Semantic Scholar API 搜尋相關論文 → 用 Claude API 分析 → 產出 markdown 研究報告，並可用網頁檢視器瀏覽。

## 從開機到看到報告

### 1. 開啟終端機，進到專案資料夾

```powershell
cd D:\research-agent
```

### 2. 啟用虛擬環境

每次開新的終端機視窗都要先啟用一次：

```powershell
.\.venv\Scripts\Activate.ps1
```

啟用成功後，提示字元前面會出現 `(.venv)`，之後可直接打 `research-agent`，不用打完整路徑。

> 如果遇到 PowerShell 執行原則的權限錯誤，可以改用完整路徑 `.\.venv\Scripts\research-agent.exe`，不啟用虛擬環境也能跑。

### 3. 產生一份新報告

```powershell
research-agent "你的研究關鍵字"
```

常用選項：
- `--limit 20` 搜尋論文數量上限（預設 20）
- `--model claude-sonnet-4-6` 指定 Claude 模型
- `--output report.md` 自訂輸出檔名（預設 `<關鍵字>_report.md`）

跑的時候會印出三個階段（搜尋論文 → Claude 分析 → 寫入報告），通常 30 秒～2 分鐘內結束。完成後目錄下會多一個 `<關鍵字>_report.md`，內含四個章節：文獻矩陣、研究趨勢、研究缺口、碩論題目建議。

### 4. 打開網頁檢視器看報告

```powershell
research-agent-view
```

會同時啟動後端伺服器（FastAPI，:8000）與前端網頁（Next.js，:3000），並自動幫你打開瀏覽器到 `http://localhost:3000`。這個指令會佔住終端機視窗（伺服器持續運行），看完前不要關掉視窗。

> 想同時跑下一個關鍵字：可以直接在網頁上的搜尋列輸入關鍵字送出，不用再開終端機；報告產生完會自動跳到該報告頁面，首頁的報告列表也會即時更新。

### 5. 看完之後關閉伺服器

回到跑 `research-agent-view` 的終端機視窗，按 `Ctrl + C` 即可停止。

## 口訣（每次使用時重複這四行）

```powershell
cd D:\research-agent                  # 1. 進資料夾
.\.venv\Scripts\Activate.ps1          # 2. 啟用環境（每個新視窗都要）
research-agent "關鍵字"                # 3. 產生報告
research-agent-view                   # 4. 開網頁看報告（Ctrl+C 關閉）
```

每次想研究新主題，重複第 3 步即可，報告會一直累積在資料夾裡，網頁檢視器都能看到。

## 前置準備（已設定好，僅供參考）

- `.env` 裡需要 `ANTHROPIC_API_KEY`（已設定）
- 第一次使用要先安裝：
  ```powershell
  pip install -e .              # CLI 核心功能
  pip install -e ".[view]"      # 網頁檢視器後端（FastAPI）
  cd web; npm install; cd ..    # 網頁檢視器前端（Next.js），只需做一次
  ```
- 網頁檢視器需要先安裝 [Node.js](https://nodejs.org/)（含 npm）。

## 疑難排解

- **Semantic Scholar 搜尋出現 rate limit 錯誤**：免費公開 API 共享配額有限，程式已內建自動重試機制，等一下再跑通常會成功。
- **Claude API 回傳 400 / credit balance too low**：到 [Anthropic Console → Plans & Billing](https://console.anthropic.com/settings/billing) 加值。
- **找不到關鍵字相關的含摘要論文**：換個更通用或不同的關鍵字再試。

更多技術細節（架構、報告格式、開發慣例）請參考 `CLAUDE.md`。
