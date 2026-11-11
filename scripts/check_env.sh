#!/usr/bin/env bash
# LinuxPulse environment verification (Member 5). Run from anywhere: ./scripts/check_env.sh
# Exit status: 0 if all REQUIRED checks pass, 1 otherwise. Optional tools only warn.
cd "$(dirname "$0")/.." || exit 1

if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY="${PYTHON:-python3}"; fi
fail=0
ok()   { printf '  [ OK ] %-11s %s\n' "$1" "$2"; }
bad()  { printf '  [FAIL] %-11s %s\n' "$1" "$2"; fail=1; }
warn() { printf '  [WARN] %-11s %s\n' "$1" "$2"; }

echo "LinuxPulse environment check (python: $PY)"

if ! command -v "$PY" >/dev/null 2>&1; then
  bad python "not found. Arch: sudo pacman -S python"
else
  if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
    ok python "$("$PY" -V 2>&1)"
  else
    bad python "$("$PY" -V 2>&1) — 3.9+ required"
  fi
  if v=$("$PY" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null); then
    ok tkinter "Tk $v"
  else
    bad tkinter "missing. Arch/Omarchy: sudo pacman -S tk   Debian: sudo apt install python3-tk"
  fi
  for mod in numpy matplotlib; do
    if v=$("$PY" -c "import $mod; print($mod.__version__)" 2>/dev/null); then
      ok "$mod" "$v"
    else
      bad "$mod" "missing. Run: make install"
    fi
  done
fi

# Required tools: collector needs top; Makefile needs make.
for t in top make; do
  if p=$(command -v "$t"); then ok "$t" "$p"; else bad "$t" "not found (Arch: sudo pacman -S procps-ng make)"; fi
done
# Profiling-only tools (needed for `make profile`, not for running the app).
for t in gcc gprof; do
  if p=$(command -v "$t"); then ok "$t" "$p"; else warn "$t" "not found; needed for profiling (Arch: sudo pacman -S gcc binutils)"; fi
done
if [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
  ok display "${WAYLAND_DISPLAY:-$DISPLAY}"
else
  warn display "no DISPLAY/WAYLAND_DISPLAY; the GUI cannot open in this session"
fi

echo
if [ $fail -eq 0 ]; then echo "Environment OK."; else echo "Environment check FAILED (see [FAIL] lines)."; fi
exit $fail
