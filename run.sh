#!/usr/bin/env bash
# One-command launcher for Linux and macOS (Intel / Apple Silicon M1–M5).
# Creates a local virtualenv on first run, installs requirements, starts the dashboard.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! "$PY" -c "import tkinter" 2>/dev/null; then
  echo "Tkinter is not available for $("$PY" -c 'import sys; print(sys.executable)')."
  case "$(uname -s)" in
    Darwin) echo "Install Python from https://www.python.org/downloads/ or: brew install python python-tk" ;;
    *)      echo "Debian/Ubuntu: sudo apt install python3-tk | Fedora: sudo dnf install python3-tkinter | Arch: sudo pacman -S tk" ;;
  esac
  exit 1
fi

if [ ! -d .venv ]; then
  "$PY" -m venv .venv
  ./.venv/bin/python -m pip install --quiet --upgrade pip
  ./.venv/bin/python -m pip install --quiet -r requirements.txt
fi
exec ./.venv/bin/python main.py "$@"
