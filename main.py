"""Entry point: python3 main.py   (Linux and macOS)"""
import sys

if sys.version_info < (3, 9):
    sys.exit("Python 3.9 or newer is required.")

try:
    import tkinter as tk
except ImportError:
    if sys.platform == "darwin":
        hint = "Install Python from python.org, or: brew install python python-tk"
    else:
        hint = ("Debian/Ubuntu: sudo apt install python3-tk   ·   Fedora: sudo dnf install python3-tkinter   ·   "
                "Arch: sudo pacman -S tk")
    sys.exit(f"Tkinter is not available for this Python ({sys.executable}).\n{hint}")

try:
    import matplotlib  # noqa: F401
except ImportError:
    sys.exit(f"Matplotlib is missing. Run:  {sys.executable} -m pip install -r requirements.txt")

import argparse

from gui.app import DashboardApp
from gui.platform_support import tk_version_warning


def make_source(demo=False, interval=1.0):
    """Live `top` data on Linux/macOS; synthetic data with --demo or if top can't be used.

    TEMPORARY: once the team's collector + analytics exist, return a source that wraps
    them (see README, "Integrating the real backend").
    """
    if not demo:
        try:
            if sys.platform.startswith("linux"):
                from live.top_linux import TopLinuxSource
                return TopLinuxSource(interval=interval)
            if sys.platform == "darwin":
                from live.top_macos import TopMacSource
                return TopMacSource(interval=interval)
            print(f"No live source for {sys.platform}; using demo data.", file=sys.stderr)
        except Exception as exc:   # top missing / unsupported
            print(f"Live data unavailable ({exc}); falling back to demo data.", file=sys.stderr)
    from dummy.dummy_source import DummySource
    return DummySource(interval=interval)


def main():
    ap = argparse.ArgumentParser(description="Unix System Monitoring Dashboard")
    ap.add_argument("--demo", action="store_true", help="use synthetic demo data instead of live top output")
    ap.add_argument("--interval", type=float, default=1.0, help="refresh interval in seconds (default 1)")
    args = ap.parse_args()

    warning = tk_version_warning()
    if warning:
        print("WARNING:", warning, file=sys.stderr)
    root = tk.Tk(className="SystemMonitor")
    DashboardApp(root, make_source(args.demo, max(0.5, args.interval)))
    root.mainloop()


if __name__ == "__main__":
    main()
