# GUI Design — Dashboard (Dhiren)

Dark, Netdata-style Tkinter dashboard. Runs on Linux (any distro, X11/Wayland) and macOS
(Intel / Apple Silicon). Matplotlib charts are embedded with `FigureCanvasTkAgg`.

## Run the dashboard

```bash
python3 main.py              # live data (Linux and macOS)
python3 main.py --demo       # synthetic data through the full pipeline, any OS (alias --mock)
```
Live data works on Linux and macOS (the collector has a macOS path). Demo data is generated in
`main.py` (`DemoCollector`) in the same shape as the collector's output, so the adapter, the
analytics engine and the GUI all run exactly as on Linux.
Needs Python 3.9+, Tk 8.6+ and matplotlib (`sudo apt install python3-tk` / `sudo pacman -S tk` /
`brew install python-tk`). Demo data is shown with a **DEMO DATA** badge.

## Files

```text
gui/
├── __init__.py          exports: Dashboard, ViewState, ProcessRow, Alert, SourceError, ProcessTable
├── dashboard.py         everything except the table, in sections:
│                          platform support (Linux/macOS) · view model (ViewState etc.) · settings
│                          (team names, website, poll interval) · theme · reusable widgets
│                          (gauges, cards, per-core bars, legends, index) · chart embedding
│                          (FigureCanvasTkAgg) · Overview / Processes / Analytics / About views
│                          · Dashboard window (rail, top bar, queue polling, shutdown)
└── process_table.py     ProcessTable: self-contained sortable / searchable / filterable
                         ttk.Treeview (no imports from dashboard.py; themed via arguments)
assets/logo.png          app logo / window icon
assets/screenshots/      overview, processes, analytics, about, edge cases
```
`visualization/plots.py` in this hand-off is an **interim** implementation so the GUI runs.
That module belongs to Pavan; see "Interfaces the GUI expects" below.

## Views

| View (shortcut) | Contents |
|---|---|
| **Overview** (Ctrl/⌘ 1) | CPU, RAM, SWAP ring gauges (red tick = peak) · System load (1/5/15 min) · Monitoring status (LIVE / STALE / PAUSED / SOURCE ERROR, interval, last update, samples) · **CPU core count** + per-core utilization · stacked CPU chart (user/system/nice/iowait/irq/softirq/steal) · RAM chart (used/buff-cache/free) · metrics index |
| **Processes** (2) | Monitoring status + task counts · Top 5 by %CPU · Recent alerts · process table: PID, USER, COMMAND, %CPU, %MEM, RES, TIME+, STATE; sortable on every column; search; filters All / High CPU / High GPU / System |
| **Analytics** (3) | Average CPU, average RAM, peak CPU / RAM / SWAP · CPU, RAM, SWAP, load histories (dashed = average) · per-core heatmap · top processes by **CPU or Memory** · active alerts |
| **About** (4) | Project name, team table, clickable website, clock, host info, memory donut |

Top bar: Play/Pause (Space), time range of the shown history, alert counts (critical / warning),
status. Gauges colour green → amber (75%) → red (90%); these are *display* colours. Alerts
themselves come from the analytics engine.

## Integration contract (for the application controller)

```python
import queue, tkinter as tk
from gui.dashboard import Dashboard
from gui.dashboard import ViewState, SourceError

updates = queue.Queue(maxsize=16)
root = tk.Tk(className="SystemMonitor")
Dashboard(root, updates, on_close=controller.stop)   # on_close: stop worker threads
controller.start(updates)      # worker thread: updates.put(to_view_state(snapshot, result))
root.mainloop()                # on failure:    updates.put(SourceError("top failed: ..."))
```

* The GUI **never blocks**: it drains the queue every 250 ms with `root.after`, keeps only the
  newest item, and touches widgets only on the Tk main thread.
* No new item for 5 s → status **STALE** (handles slow collection).
* Closing the window (or ⌘Q on macOS) cancels all `after` jobs, calls `on_close`, then destroys.

### Mapping onto `ViewState` (one adapter function during integration)

| ViewState field | From |
|---|---|
| `timestamp`, `cpu`, `cpu_dims` (us/sy/ni/wa/hi/si/st/id), `per_core` | collector snapshot (top header, `%CpuN` lines) |
| `load` (1, 5, 15), `uptime_s`, `n_cpus` | collector |
| `ram`, `mem_total/used/free/buffcache/available_gib`, `swap`, `swap_used/total_gib` | collector (`MiB Mem` / `MiB Swap` lines) |
| `total`, `running`, `sleeping`, `stopped`, `zombie` | collector (`Tasks:` line) |
| `processes: [ProcessRow(pid, name, cpu, mem, state, user, res_mib, time_s, is_system)]` | collector process table |
| `history` (t relative to timestamp, cpu, ram, swap, load1, cpu_dims, per_core, mem_*) | analytics engine sample history (300 samples) |
| `avg_cpu`, `avg_ram`, `peak_cpu`, `peak_ram`, `peak_swap` | analytics engine |
| `top_processes` (by CPU), `top_memory_processes` (by MEM) | analytics engine |
| `alerts: [Alert(level, message, timestamp)]` | analytics engine (99% CPU, 85% RAM, 90% swap) |
| `interval_s`, `hostname` | config / controller |

**Missing data rule:** any field may be `None`. The GUI shows "—" / "unavailable" and never
treats `None` as 0. An empty `processes` list is valid. `per_core=None` shows "not provided";
`swap_total_gib == 0` shows "no swap configured"; `gpu_available=False` makes the High GPU filter
explain that GPU telemetry is unavailable.

## Interfaces the GUI expects from `visualization/`

The GUI only embeds `obj.figure` and calls `obj.update(...)`. It never recreates figures:

| Class | Used in | Update call |
|---|---|---|
| `StackedAreaPlot(dims, window, ylim, ylabel, yfmt)` + `set_hidden(keys)` | Overview CPU and RAM charts | `update(times_epoch, {dim: values}, ymax=None)` |
| `AnalyticsGrid(colors, window)` | Analytics history + per-core heatmap | `update(history, now_epoch, {"cpu": avg, "ram": avg})` |
| `MemoryPie()` | About | `update(used_gib, available_gib)` |

Values may contain `None` (drawn as gaps). The interim implementations update existing
`Line2D` / image artists and only replace fill polygons.

## Edge cases verified

Large process lists (diffed `Treeview` updates, preserves selection and scroll) · empty process
list · missing fields (`RES`, `%MEM`, swap, per-core) · 2–32+ CPUs · 1100×700 minimum window ·
pause/resume · STALE after slow collection · clean shutdown with the worker thread stopped.
