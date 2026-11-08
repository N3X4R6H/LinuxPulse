#!/usr/bin/env bash
# LinuxPulse launcher — Linux and macOS.
#
#   ./run.sh                     start the dashboard with live data (Linux and macOS)
#   ./run.sh --demo              start with demo data (also: --mock, --interval N)
#   ./run.sh test                run the unit tests
#   ./run.sh clean               delete the local virtual environment (.venv)
#
# First run creates .venv and installs requirements.txt; it reinstalls automatically
# when requirements.txt changes. Use another interpreter with:  PYTHON=python3.12 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENV=".venv"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: $PY not found. Install Python 3.9 or newer." >&2
  exit 1
fi

if [ "${1:-}" = "clean" ]; then
  rm -rf "$VENV"
  echo "Removed $VENV"
  exit 0
fi

"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "error: Python 3.9+ is required (found $("$PY" -V 2>&1))." >&2
  exit 1
}

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
  echo "error: Tkinter is not available for $("$PY" -c 'import sys; print(sys.executable)')." >&2
  case "$(uname -s)" in
    Darwin) echo "  Install Python from https://www.python.org/downloads/  or:  brew install python python-tk" >&2 ;;
    *)      echo "  Debian/Ubuntu: sudo apt install python3-tk   Fedora: sudo dnf install python3-tkinter   Arch: sudo pacman -S tk" >&2 ;;
  esac
  exit 1
fi

TKV="$("$PY" -c 'import tkinter; print(tkinter.TkVersion)')"
if [ "${TKV%%.*}" -lt 8 ] || { [ "${TKV%%.*}" -eq 8 ] && [ "${TKV#*.}" -lt 6 ]; }; then
  echo "warning: Tk $TKV detected; Tk 8.6+ is needed for correct rendering." >&2
  [ "$(uname -s)" = "Darwin" ] && echo "  Use Python from python.org or Homebrew (brew install python python-tk), not /usr/bin/python3." >&2
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtual environment in $VENV ..."
  "$PY" -m venv "$VENV"
fi

# (Re)install dependencies when requirements.txt is new or has changed.
STAMP="$VENV/.requirements.sha256"
WANT="$("$VENV/bin/python" -c 'import hashlib; print(hashlib.sha256(open("requirements.txt", "rb").read()).hexdigest())')"
if [ "$(cat "$STAMP" 2>/dev/null || true)" != "$WANT" ]; then
  echo "Installing dependencies from requirements.txt ..."
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r requirements.txt
  echo "$WANT" > "$STAMP"
fi

if [ "${1:-}" = "test" ]; then
  shift
  exec "$VENV/bin/python" -m unittest discover -s tests -v "$@"
fi

exec "$VENV/bin/python" main.py "$@"
