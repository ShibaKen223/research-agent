@echo off
cd /d "%~dp0"
echo Research Agent 啟動中，請稍候，瀏覽器會自動開啟...
"%~dp0.venv\Scripts\research-agent-view.exe"
pause
