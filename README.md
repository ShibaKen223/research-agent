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

## 在新電腦從零開始安裝（換電腦／重灌後）

> 程式碼全部都在 GitHub 上（`https://github.com/ShibaKen223/research-agent`，私有 repo）。
> 換電腦時**不用**手動搬資料夾，照下面步驟重新拉下來、重建環境即可。
> 注意：`.env`（API key）和產出的報告（`*_report.md`）**不會**進 git（刻意排除，避免外洩／雜訊），
> 所以新電腦上要自己補一個 `.env`；舊報告沒搬過去也沒關係，隨時可以重跑產生。

### 0. 先裝好這三個工具

- [Git](https://git-scm.com/)
- [Python 3.10 以上](https://www.python.org/)（安裝時勾選「Add Python to PATH」）
- [Node.js](https://nodejs.org/)（含 npm，網頁檢視器才需要）

### 1. 把專案拉下來

```powershell
cd D:\                                                   # 想放哪都行
git clone https://github.com/ShibaKen223/research-agent.git
cd research-agent
```

### 2. 建立並啟用虛擬環境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安裝相依套件

```powershell
pip install -e ".[view]"      # 一次裝好 CLI 核心 + 網頁檢視器後端
cd web; npm install; cd ..    # 網頁檢視器前端（Next.js），只需做一次
```

### 4. 補上 `.env`（放 API key）

在專案根目錄建立一個 `.env` 檔，內容一行：

```
ANTHROPIC_API_KEY=sk-ant-...
```

key 去 [Anthropic Console → API Keys](https://console.anthropic.com/settings/keys) 看／重新產生，
或從舊電腦的 `.env` 複製過來（建議順手存進密碼管理器，這樣下次換電腦直接貼）。

裝完這四步，就能照上面「從開機到看到報告」的口訣正常使用了。

## 前置準備（本機已設定好，僅供參考）

上面「從新電腦安裝」是完整流程；這台電腦其實已經做完了，平常只要用上面的四行口訣即可。

## 疑難排解

- **Semantic Scholar 搜尋出現 rate limit 錯誤**：免費公開 API 共享配額有限，程式已內建自動重試機制，等一下再跑通常會成功。
- **Claude API 回傳 400 / credit balance too low**：到 [Anthropic Console → Plans & Billing](https://console.anthropic.com/settings/billing) 加值。
- **找不到關鍵字相關的含摘要論文**：換個更通用或不同的關鍵字再試。

更多技術細節（架構、報告格式、開發慣例）請參考 `CLAUDE.md`。
