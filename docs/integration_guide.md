# LINUXPULSE — Integration Guide

**Owner:** Member 5 (integration)
**Audience:** Members 1, 2, 3, 4
**Status:** Stage 1 — interface contracts

This document defines the exact contracts each module must implement so
that the pieces integrate without negotiation. It deliberately does **not**
prescribe an implementation — only inputs, outputs, names, types, error
behaviour and one example per module.

All shared data shapes live in [`../models.py`](../models.py); all tunable
parameters live in [`../config.py`](../config.py). Read those two files
first. Field names and units there are normative for this guide.

**Unit conventions (from `models.py`):** memory in bytes (`*_bytes`),
percentages as `float` 0-100 (`*_percent`), counts as `int` (`*_count`),
timestamps as POSIX epoch seconds (`float`). Unavailable measurements are
`None`, never `0`.

---

## Shared runtime context

Every constructor that needs configuration takes a single
`config.AppConfig` argument (use `config.DEFAULT_CONFIG` by default). Do
not read configuration from any other source. Every constructor that needs
to stop cleanly takes a `threading.Event` named `stop_event`.

```python
import config
from models import SystemSnapshot
stop_event = threading.Event()
cfg = config.DEFAULT_CONFIG
```

---

## Member 1 — Collector

**Package:** `collector/`
**Files to implement:** `collector/__init__.py`, `collector/top_collector.py`,
`collector/parser.py`

### `collector.parser`

| | |
| --- | --- |
| **Purpose** | Convert raw `top -b` text into a `SystemSnapshot`. |
| **Function** | `parse_top_output(raw_text: str, *, timestamp: float \| None = None) -> SystemSnapshot` |
| **Input** | `raw_text`: the full stdout of one `top -b -n 1 -H` invocation, as a single string. `timestamp`: optional epoch seconds; defaults to `time.time()`. |
| **Output** | A `models.SystemSnapshot` with `cpu`, `memory`, `swap` (or `None` if the host has no swap), and `processes` (up to `config.default_process_count` rows). |
| **Error behavior** | A field that cannot be parsed is set to `None` (or `0` for counts) — the function does **not** raise on a partial parse. It raises `ParseError` only when the input is not recognizable as `top` output at all (e.g. empty, or a shell error message). |
| **Exception type** | `collector.parser.ParseError(Exception)` — define and export it. |

Example contract:

```python
from collector.parser import parse_top_output, ParseError
from models import SystemSnapshot

raw = run_top_once()  # str
try:
    snapshot = parse_top_output(raw)
except ParseError:
    snapshot = SystemSnapshot.empty()
assert isinstance(snapshot, SystemSnapshot)
# memory in bytes, percentages 0-100, missing fields are None
```

### `collector.top_collector`

| | |
| --- | --- |
| **Purpose** | Drive `top` on a timer and push snapshots into a queue. |
| **Class** | `TopCollector(config: AppConfig, output_queue: queue.Queue[SystemSnapshot], stop_event: threading.Event)` |
| **Methods** | `start() -> None` (spawns the daemon thread named `config.collector_thread_name`); `join(timeout: float \| None = None) -> None`. |
| **Input** | Reads `config.top_binary`, `top_batch_mode`, `top_iterations`, `top_show_threads`, `sampling_interval_seconds`, `default_process_count`. |
| **Output** | Pushes one `SystemSnapshot` per tick into `output_queue`. On a subprocess/parse failure pushes `SystemSnapshot.empty()`. If the queue is full it drops the oldest pending item (`queue.get_nowait` then re-put) before pushing the fresh one. |
| **Error behavior** | Never raises out of the worker thread; logs to stderr and continues. Subprocess is terminated with `top_terminate_timeout_seconds` on stop. |

Example contract:

```python
import queue, threading, config
from collector.top_collector import TopCollector
from models import SystemSnapshot

cfg = config.DEFAULT_CONFIG
q: "queue.Queue[SystemSnapshot]" = queue.Queue(maxsize=cfg.queue_capacity)
stop = threading.Event()
collector = TopCollector(cfg, q, stop)
collector.start()
snap = q.get(timeout=10)         # blocks up to 10s for first sample
assert isinstance(snap, SystemSnapshot)
stop.set(); collector.join(timeout=cfg.shutdown_timeout_seconds)
```

---

## Member 2 — Analytics

**Package:** `analytics/`
**Files to implement:** `analytics/__init__.py`, `analytics/engine.py`

### `analytics.engine`

| | |
| --- | --- |
| **Purpose** | Maintain the history ring buffer and reduce it into `AnalyticsResult` + alerts. |
| **Class** | `AnalyticsEngine(config: AppConfig)` |
| **Methods** | `record(snapshot: SystemSnapshot) -> None` (append to internal `deque(maxlen=config.history_limit)`); `analyze() -> AnalyticsResult` (reduce current history); `history() -> collections.deque[SystemSnapshot]` (read-only view for visualization). |
| **Input** | `SystemSnapshot` via `record`; thresholds from `config.cpu_threshold_percent`, `ram_threshold_percent`, `swap_threshold_percent`. |
| **Output** | `models.AnalyticsResult` with `cpu`/`memory`/`swap` `MetricStatistics`, `top_cpu_processes` / `top_memory_processes` (from the most recent snapshot), and `alerts` (`AlertInfo` for each breached threshold). `sample_count` and `window_seconds` reflect the history actually held. |
| **Error behavior** | Empty history → `AnalyticsResult.empty()`. All-`None` metric → `MetricStatistics` with every field `None`. `usage_percent` of `None` or `total_bytes == 0` → that sample is skipped for averages, never produces a divide-by-zero. Never raises. |

Statistics semantics (so M3 and M4 agree on what the numbers mean):

* `current` = value from the most recent valid sample.
* `average` / `minimum` / `maximum` = over valid (non-`None`) samples in
  the window.
* `trend_slope` = slope of a least-squares linear fit of value vs. time,
  in **percent per second**; `None` when fewer than two valid samples.

Example contract:

```python
import config
from analytics.engine import AnalyticsEngine
from models import SystemSnapshot, AnalyticsResult

cfg = config.DEFAULT_CONFIG
engine = AnalyticsEngine(cfg)
engine.record(snapshot_a)
engine.record(snapshot_b)
result = engine.analyze()
assert isinstance(result, AnalyticsResult)
history = engine.history()          # deque, for visualization
```

### Analytics worker thread (wired by M5 in Stage 2)

M2 may optionally provide `AnalyticsEngine.run(input_queue, stop_event)`
that loops `record` + `analyze`. If not, M5 wires a thread in `main.py`
that does:

```python
snap = input_queue.get()
engine.record(snap)
latest_result = engine.analyze()
```

Either way, the contract above is what the GUI consumes.

---

## Member 3 — GUI

**Package:** `gui/`
**Files to implement:** `gui/__init__.py`, `gui/dashboard.py`,
`gui/process_table.py`

### `gui.dashboard`

| | |
| --- | --- |
| **Purpose** | Build and drive the Tkinter root window. |
| **Class** | `Dashboard(config: AppConfig, *, on_close: Callable[[], None] \| None = None)` |
| **Methods** | `update(snapshot: SystemSnapshot, result: AnalyticsResult) -> None` (called on the main thread, schedules a redraw); `run() -> None` (enters `mainloop()`); `close() -> None`. |
| **Input** | Latest `SystemSnapshot` + `AnalyticsResult`, passed in by the lifecycle layer on each tick. Configuration from `config` (refresh interval, thresholds, memory display unit). |
| **Output** | Renders the window; embeds Matplotlib figures supplied by M4 via `matplotlib.backends.backend_tkagg.FigureCanvasTkAgg`. Calls `config.gui_refresh_interval_seconds` via `root.after`. |
| **Error behavior** | A `None` field renders as "—" (use `config.format_memory`). An exception inside a refresh callback is caught at the `after()` boundary, logged, and the next tick proceeds. The window never closes itself on a data error. |

### `gui.process_table`

| | |
| --- | --- |
| **Purpose** | The scrollable process list widget. |
| **Class** | `ProcessTable(parent: tkinter.Widget, config: AppConfig)` |
| **Methods** | `update(processes: list[ProcessInfo]) -> None` (rebuild rows in place from `snapshot.processes`); `clear() -> None`. |
| **Columns** | PID, Name, CPU%, MEM%, User, State — matching `models.ProcessInfo` fields exactly. |
| **Error behavior** | Empty list → a single placeholder row "No processes". `None` fields render as "—". |

Example contract:

```python
import config
from gui.dashboard import Dashboard
from gui.process_table import ProcessTable
from models import SystemSnapshot, AnalyticsResult

cfg = config.DEFAULT_CONFIG
dash = Dashboard(cfg, on_close=lambda: stop_event.set())
# ... on each GUI tick, called on the main thread:
dash.update(snapshot, analytics_result)
# initially:
dash.update(SystemSnapshot.empty(), AnalyticsResult.empty())
dash.run()
```

> **Tkinter threading rule:** `Dashboard.update` and `ProcessTable.update`
> are called only from the main thread. The lifecycle layer (M5) is
> responsible for ensuring the analytics thread does not call them
> directly.

---

## Member 4 — Visualization

**Package:** `visualization/`
**Files to implement:** `visualization/__init__.py`, `visualization/plots.py`

### `visualization.plots`

Pure functions: history in, Matplotlib `Figure` out. No Tkinter imports,
no side effects, no I/O.

| Function | Input | Output |
| --- | --- | --- |
| `plot_cpu_history(history: collections.deque[SystemSnapshot] \| list[SystemSnapshot]) -> matplotlib.figure.Figure` | snapshots with `cpu.usage_percent` | Figure with CPU% over time, threshold line at `config.cpu_threshold_percent` |
| `plot_memory_history(history) -> Figure` | snapshots with `memory.usage_percent` | Figure with RAM% (and swap% if present) over time |
| `plot_top_processes(processes: list[ProcessInfo], *, sort_by: str = "cpu") -> Figure` | a process list | horizontal bar chart of top N by `cpu_percent` or `memory_percent` |
| `empty_figure(message: str = "No data") -> Figure` | — | placeholder figure |

| | |
| --- | --- |
| **Error behavior** | Empty / all-`None` history → `empty_figure(...)`, never raises. Missing swap → that line is simply omitted. |
| **Units** | X axis is seconds relative to the newest sample (or epoch); Y axis is percent 0-100 for CPU/memory, bytes→display unit via `config.convert_bytes` where absolute memory is shown. Use `config.memory_display_unit` for labels. |
| **Threading** | These functions may be called from the GUI thread (fast enough for 300 points) or from the analytics thread; they must not mutate the input deque (iterate over `list(history)`). |

Example contract:

```python
import config
from visualization.plots import plot_cpu_history, plot_top_processes
from analytics.engine import AnalyticsEngine

cfg = config.DEFAULT_CONFIG
engine = AnalyticsEngine(cfg)
fig = plot_cpu_history(engine.history())
fig_top = plot_top_processes(engine.history()[-1].processes, sort_by="cpu")
# GUI embeds: FigureCanvasTkAgg(fig, master=root).get_tk_widget().pack()
```

---

## Integration order

Stage 2 integration proceeds bottom-up so each layer has something real to
consume:

1. **M1 collector** + `tests/test_parser.py`, `tests/test_collector.py` —
   produces real `SystemSnapshot` objects.
2. **M2 analytics** + `tests/test_analytics.py` — consumes snapshots,
   produces `AnalyticsResult`.
3. **M4 visualization** + `tests/test_visualization.py`,
   `tests/test_integration.py` — consumes history, produces figures.
4. **M3 GUI** — consumes snapshots + results + figures, renders.
5. **M5 `main.py`** — wires threads, queue, lifecycle; smoke test.

Each step must pass `make test` (Stage 2 deliverable) before the next
begins. See [`development_workflow.md`](./development_workflow.md) for
branch and PR rules.
