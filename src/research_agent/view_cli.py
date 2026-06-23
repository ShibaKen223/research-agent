"""Console-script wrapper: `research-agent-view` launches the FastAPI backend
and the Next.js web frontend (web/), then opens the dashboard in a browser.
"""

import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def main():
    if not WEB_DIR.exists():
        sys.exit(f"找不到 web 前端目錄：{WEB_DIR}")

    npm = shutil.which("npm")
    if npm is None:
        sys.exit("找不到 npm，請先安裝 Node.js，並在 web/ 目錄執行一次 `npm install`。")

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "research_agent.api:app", "--port", "8000"]
    )
    frontend = subprocess.Popen([npm, "run", "dev"], cwd=WEB_DIR)

    time.sleep(2)
    webbrowser.open("http://localhost:3000")

    try:
        frontend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (frontend, backend):
            proc.terminate()
        for proc in (frontend, backend):
            proc.wait()


if __name__ == "__main__":
    main()
