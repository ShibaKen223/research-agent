"""Console-script wrapper: `research-agent-view` launches the FastAPI backend
and the Next.js web frontend (web/), then opens the dashboard in a browser.
"""

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = _PROJECT_ROOT / "web"


def _lan_ip() -> str:
    """Best-effort LAN IP (the address other devices on the same Wi-Fi would use).

    Doesn't actually send packets — just asks the OS which local interface
    would be used to reach an external address.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    if not WEB_DIR.exists():
        sys.exit(f"找不到 web 前端目錄：{WEB_DIR}")

    npm = shutil.which("npm")
    if npm is None:
        sys.exit("找不到 npm，請先安裝 Node.js，並在 web/ 目錄執行一次 `npm install`。")

    lan_ip = _lan_ip()
    # A fresh token per run: anyone on the same Wi-Fi can reach the backend
    # once it's bound to 0.0.0.0, and without this they could trigger paid
    # Claude API calls. The frontend bakes the token in automatically, so
    # phones on the same network just open the URL below — no manual step.
    token = secrets.token_urlsafe(16)
    child_env = {
        **os.environ,
        "RESEARCH_AGENT_TOKEN": token,
        "NEXT_PUBLIC_API_URL": f"http://{lan_ip}:8000",
        "NEXT_PUBLIC_API_TOKEN": token,
        # Always anchor reports to the project root so desktop shortcuts or other
        # launchers that don't cd first still find existing reports.
        "REPORTS_DIR": str(_PROJECT_ROOT),
    }

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "research_agent.api:app", "--host", "0.0.0.0", "--port", "8000"],
        env=child_env,
        cwd=_PROJECT_ROOT,
    )
    frontend = subprocess.Popen([npm, "run", "dev"], cwd=WEB_DIR, env=child_env)

    print(f"本機使用：http://localhost:3000")
    print(f"同一 Wi-Fi 下的其他裝置（手機等）：http://{lan_ip}:3000")

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
