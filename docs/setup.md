# LinuxPulse — Setup and Build Automation

All commands run from the repository root.

```bash
sudo pacman -S python tk gcc make binutils procps-ng   # Arch / Omarchy, one time
make install      # .venv + requirements.txt
make check        # environment verification (scripts/check_env.sh)
make mock         # GUI with synthetic data   (ARGS='--interval 1' for extra flags)
make run          # GUI with live data from top
make test         # unittest discovery over tests/
make profile      # runs scripts/profile.sh (see "Known dependency")
make clean        # caches, gmon.out, *.log, benchmark binaries; keeps .venv
make help
```

## Arch Linux / Omarchy notes

- **PEP 668:** Arch marks the system Python as externally managed, so `pip install` outside a
  virtual environment fails. `make install` therefore always uses `.venv`; the other targets pick
  `.venv/bin/python` automatically when it exists. Do not use `--break-system-packages`.
- **Tkinter** is not a pip package. On Arch it comes from the `tk` package. `make install` only
  prints this hint; it never runs `sudo` itself.
- **gprof** is part of `binutils`; **top** is in `procps-ng`; `gcc` also provides `g++` for the C++ benchmark.
- **Wayland (Hyprland):** Tk runs through XWayland. If `make check` reports no display, run from a
  graphical terminal session, not a bare TTY or SSH without forwarding.
- **Python version:** Arch tracks the newest Python. If a wheel is missing for it, use another
  interpreter: `make install SYS_PY=python3.12` (after removing `.venv`).
- `run.sh` (Linux/macOS launcher) manages its own `.venv` and remains available; `scripts/launch.sh`
  is owned by Member 1 and is not touched by the Makefile.

## Dependencies

`requirements.txt` holds runtime packages only (`numpy`, `matplotlib`). Testing uses the standard
library `unittest`; no dev packages are required.

## Known dependency

`make profile` calls `scripts/profile.sh`, which is not in the repository yet. Until it lands the
target exits with an explanatory error instead of pretending to succeed.
