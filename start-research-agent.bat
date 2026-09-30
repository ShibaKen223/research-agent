@echo off
rem Keep this file CRLF + UTF-8 (see .gitattributes). chcp 65001 must run before
rem any non-ASCII line, otherwise cmd on a Big5 (cp950) system misparses it.
chcp 65001 >nul
cd /d "%~dp0"
set "REPORTS_DIR=%~dp0"

if not exist "%~dp0.venv\Scripts\research-agent-view.exe" (
    echo [錯誤] 找不到 "%~dp0.venv\Scripts\research-agent-view.exe"
    echo 請在專案資料夾執行：
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -e ".[view]"
    goto :end
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [錯誤] 找不到 npm，請先安裝 Node.js 後重新開機再試。
    goto :end
)

if not exist "%~dp0web\node_modules" (
    echo 第一次啟動：正在安裝前端依賴（npm install），請稍候...
    pushd "%~dp0web"
    call npm install
    popd
)

echo Research Agent 啟動中，請稍候，瀏覽器會自動開啟...
"%~dp0.venv\Scripts\research-agent-view.exe"

:end
pause
