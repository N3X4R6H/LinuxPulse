# Unix System Monitor — GUI

Netdata-style dark Tkinter dashboard (Introduction · Overview · Processes · Analytics).

**Data source:** by default it shows **live data from the machine it runs on**, read from `top`
(`live/`, a temporary stand-in until the team's collector is wired in). `--demo` switches to
synthetic data, shown with a `DEMO DATA` badge.

```bash
./run.sh                    # live data (Linux: procps top · macOS: BSD top)
./run.sh --demo             # synthetic demo data
./run.sh --interval 2       # refresh every 2 s
```

| | Linux (`top -b -1`) | macOS (`top -l`) |
|---|---|---|
| CPU total + user/system | ✓ | ✓ |
| nice / iowait / irq / softirq / steal | ✓ | — (not reported) |
| Per-core utilization | ✓ | — (not reported) |
| RAM used / free / buff-cache / available | ✓ | used / unused (no buff-cache) |
| Swap, load average, uptime, tasks | ✓ | ✓ (swap via `sysctl`) |
| Process table (PID USER CMD %CPU %MEM RES TIME+ S) | ✓ | ✓ |
| System-process filter | UID < 1000 | UID < 500 / `_daemon` users |
| GPU | — (needs a GPU collector) | — |

Anything a platform doesn't report is shown as "—" or "unavailable", never as a made-up number.
If `top` can't be started, the app falls back to demo data and says why in the terminal.

## Run

Quickest (Linux or macOS): `./run.sh`. It creates a `.venv`, installs matplotlib on first run, then starts the app.

Requirements: **Python 3.9+** with **Tk 8.6+** (Tk 9 also works) and matplotlib.

### Linux (any distro, X11 or Wayland)
```bash
sudo apt install python3-tk            # Debian/Ubuntu/Mint
# sudo dnf install python3-tkinter     # Fedora/RHEL
# sudo pacman -S tk                    # Arch/Manjaro
python3 -m pip install -r requirements.txt
python3 main.py
```

### macOS (Intel and Apple Silicon M1–M5)
Use Python from **python.org** (includes Tk) or **Homebrew**:
```bash
brew install python python-tk          # or install from https://www.python.org/downloads/
python3 -m pip install -r requirements.txt
python3 main.py
```
Don't use the Xcode/system `/usr/bin/python3`: it ships Tk 8.5, which renders this theme badly.
The app prints a warning if it detects that.

Optional typography: IBM Plex (`sudo apt install fonts-ibm-plex`, or `brew install --cask font-ibm-plex-sans font-ibm-plex-mono`).
Otherwise it falls back to SF / Helvetica Neue / Menlo on macOS and Inter / Ubuntu / DejaVu on Linux.

### Platform handling (`gui/platform_support.py`)
- Shortcuts use **⌘ on macOS** (Ctrl also works there) and **Ctrl on Linux**.
- Font sizes are normalised: Aqua Tk renders at 72 dpi vs ~96 dpi on X11, so fonts are scaled to look the same.
- Starts maximised on screens ≤ 1600 px wide (13–14" MacBooks, laptops).
- macOS: ⌘Q and the app menu's Quit go through the same clean shutdown as closing the window.

| Key (Linux / macOS) | Action |
|---|---|
| `Ctrl+1 … 4` / `⌘1 … 4` | switch view |
| `Space` | pause / resume live updates (collection keeps running) |
| `Ctrl+F` / `⌘F`, `Esc` | focus / clear process search |
| click a legend item | hide / show that chart dimension |
| click a column heading | sort (again to reverse) |

Edge-case testing with the dummy source:

```bash
DASH_DUMMY_CORES=32 python3 main.py   # many CPUs (per-core switches to heat tiles)
DASH_DUMMY_EMPTY=1  python3 main.py   # empty process list
DASH_DUMMY_NOSWAP=1 python3 main.py   # swap unavailable
```

## Files

```text
main.py                     entry point (DummySource → DashboardApp)
gui/
  app.py                    window, icon rail, top bar (play/pause, range, alerts), section header, live loop
  styles.py                 palette, CPU/memory dimension colours, fonts, ttk styles
  widgets.py                Panel, RingGauge, GaugeCard, NumberCard, PerCoreBars, DimensionLegend,
                            IndexPanel, RailButton, TimeRuler, PlayButton, AlertList, BarList, TabControl, ...
  process_table.py          top-style sortable/searchable/filterable ttk.Treeview
  graph_panel.py            ChartPanel: FigureCanvasTkAgg + legend
  controller.py             DataPump: background thread + queue.Queue
  view_state.py             GUI-side view model (fields map to top's output)
  config.py                 team details, timing, thresholds  ← fill in
  views/                    intro.py, overview.py, processes.py, analytics.py
visualization/plots.py      StackedAreaPlot, MemoryPie, AnalyticsGrid (+ per-core heatmap) — no Tkinter
live/top_linux.py           TEMPORARY live source: procps top parser (Linux)
live/top_macos.py           TEMPORARY live source: BSD top parser (macOS)
live/top_stream.py          runs one long-lived top process, yields complete frames
live/analytics_lite.py      TEMPORARY history / averages / peaks / alerts
dummy/dummy_source.py       synthetic data for --demo
docs/gui_design.md          layout and component hierarchy
docs/screenshots/           reference screenshots
```

## Integrating the real backend

1. Write `gui/adapter.py`: `to_view_state(snapshot, analytics) -> ViewState`, based on `models.py`.
2. Wrap collector + analytics in an object with `run(stop_event, out_queue)` that puts
   adapted `ViewState`s on the queue.
3. Return it from `make_source()` in `main.py` instead of the `live/` sources.

**Live data on macOS:** the GUI runs on both systems, but macOS `top` prints a different (BSD)
format: no `%Cpu(s): us sy ni wa hi si st` line, no per-CPU lines, no iowait or steal.
A Linux `top` parser won't read it. On a Mac, either demo with the dummy source, or give the
collector a macOS path. Fields macOS can't provide simply stay `None` and the GUI shows "—".

Per-core data comes from top's per-CPU lines (`top -b -1`, or press `1` interactively).
If the collector doesn't provide them, `per_core=None` and the GUI says so instead of
inventing numbers. The High GPU filter stays "unavailable" unless `gpu_available` is true.
