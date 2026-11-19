"""One-command launcher for the OSRS arb tool.

Usage:
    python run.py                 # start server (open http://127.0.0.1:8000/ yourself)
    python run.py --browser       # also auto-open the browser
    python run.py --setup         # force dependency reinstall
    python run.py --port 9000

First run creates backend/.venv and installs requirements automatically.
"""
import argparse
import os
import pathlib
import subprocess
import threading
import venv
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
VENV_DIR = BACKEND / ".venv"
IS_WIN = os.name == "nt"
VENV_PY = VENV_DIR / ("Scripts/python.exe" if IS_WIN else "bin/python")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the OSRS arb tool (backend + UI in one process).")
    ap.add_argument("--setup", action="store_true", help="force dependency reinstall")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--browser", action="store_true", help="auto-open the browser")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}/"

    if not VENV_PY.exists():
        print("First run: creating virtual environment ...")
        venv.create(VENV_DIR, with_pip=True)

    marker = VENV_DIR / ".deps_ok"
    if args.setup or not marker.exists():
        print("Installing dependencies ...")
        subprocess.check_call(
            [str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(BACKEND / "requirements.txt")]
        )
        marker.write_text("ok")

    if args.browser:
        threading.Timer(4.0, lambda: webbrowser.open(url)).start()

    print(f"Serving on {url}  (Ctrl+C to stop)")
    try:
        return subprocess.call(
            [str(VENV_PY), "-m", "uvicorn", "app.main:app", "--port", str(args.port)],
            cwd=str(BACKEND),
        )
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
