#!/bin/bash
# macOS launcher: double-click in Finder (or via a Desktop alias) to open the
# report viewer. Lives in the project root so it always finds .venv and web/.
cd "$(dirname "$0")" || exit 1
export REPORTS_DIR="$PWD"
# Finder-launched shells don't load ~/.zshrc, so add Homebrew's paths for npm.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

fail() { echo; echo "[錯誤] $1"; echo; read -n 1 -s -r -p "按任意鍵關閉視窗..."; exit 1; }

[ -x .venv/bin/research-agent-view ] || fail "找不到 .venv/bin/research-agent-view，請在專案資料夾執行：
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e \".[view]\""
command -v npm >/dev/null || fail "找不到 npm，請先執行：brew install node"
if [ ! -d web/node_modules ]; then
    echo "第一次啟動：正在安裝前端依賴（npm install），請稍候..."
    (cd web && npm install) || fail "npm install 失敗"
fi

echo "Research Agent 啟動中，請稍候，瀏覽器會自動開啟...（關閉：Ctrl+C）"
.venv/bin/research-agent-view
