# LinuxPulse — Release Checklist

Run from the repository root. Tick only what you actually ran; record the date and the machine.

## 1. Clean checkout
- [ ] `git status` shows no unintended files (no `.venv/`, `__pycache__/`, `gmon.out`, benchmark binaries, logs).
- [ ] Fresh clone (or `git ls-files -co --exclude-standard` copy) into an empty directory.
- [ ] `make install` completes (creates `.venv`, installs `requirements.txt`; no sudo).
- [ ] `make check` prints `Environment OK.` (Python 3.9+, Tkinter, NumPy, Matplotlib, top, make, gcc, gprof).

## 2. Automated tests
- [ ] `make test` — all tests pass (expect 0 failures; real-collector and GUI tests are skipped only if no display / non-Linux).
- [ ] `.venv/bin/python -m unittest tests.test_gui_integration -v` on a machine with a display: all 4 pass.

## 3. Manual smoke test
- [ ] `make mock`: window opens, "DEMO DATA" badge visible, status LIVE, charts and process table update, Overview / Processes / Analytics / About all open (Ctrl+1..4).
- [ ] `make run`: no badge, real process list, status LIVE; values plausible vs `top`.
- [ ] Pause (Space) freezes the display; resume catches up.
- [ ] Close the window: terminal returns promptly, `pgrep -f "main.py"` shows nothing, no stray `top`.
- [ ] Force an alert: `LINUXPULSE_RAM_THRESHOLD_PERCENT=1 make run` shows a red badge and a CRITICAL entry under Processes.

## 4. Profiling experiment
- [ ] `make profile` then `./scripts/profile.sh --impl optimized` then `./scripts/compare_profiles.sh`: parameters identical, `RESULT lines identical`.
- [ ] `profiling/results/*.txt` committed intentionally; `gmon.out` and binaries not committed.

## 5. Documentation
- [ ] README commands work as written (`make install/run/mock/test/profile/clean/help`, `./run.sh`).
- [ ] `docs/integration_guide.md`, `docs/setup.md`, `docs/performance_analysis.md` match the current code.
- [ ] No references to files that do not exist (`scripts/launch.sh` is Member 1's and still pending).

## 6. Open items before tagging
- [ ] Member 1 delivers or drops `scripts/launch.sh`.
- [ ] Owners decide on the reported items (per-core CPU, warning severity, chart layout cost) — see integration guide.
- [ ] Tag: `git tag -a v1.0 -m "LinuxPulse release"` (only after all boxes above are ticked).
