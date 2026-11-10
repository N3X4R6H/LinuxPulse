# LINUXPULSE — Integration Guide

**Owner:** Member 5 (integration)
**Audience:** Members 1, 2, 3, 4
**Status:** Stage 1 interface contracts + Stage 2 controller wiring

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

The controller (`main.py`, Member 5) owns the `queue.Queue`, the
`stop_event`, and the `on_close` callback handed to the dashboard; member
modules receive these from the controller and must not create their own.

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
| **Methods** | `start() -> None` (spawns the daemon thread named `config.collector_thread_name`); `join(timeout: float \| None = None) -> None`. `is_alive() -> bool` is optional but recommended so the controller can log a dangling thread on shutdown. |
| **Input** | Reads `config.top_binary`, `top_batch_mode`, `top_iterations`, `top_show_threads`, `sampling_interval_seconds`, `default_process_count`. The queue and stop event are supplied by the controller. |
| **Output** | Pushes one `SystemSnapshot` per tick into `output_queue`. On a subprocess/parse failure pushes `SystemSnapshot.empty()`. If the queue is full it drops the oldest pending item (`queue.get_nowait` then re-put) before pushing the fresh one. |
| **Error behavior** | Never raises out of the worker thread; logs to stderr and continues. Subprocess is terminated with `top_terminate_timeout_seconds` on stop. Checks `stop_event` each loop so shutdown is prompt. |

The mock-mode drop-in `mock_source.MockCollector` implements exactly this
contract; the controller swaps them via `build_application(mock=True)`.

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

### Analytics execution model (wired by M5 in Stage 2)

Analytics runs **on the GUI main thread**, inside the controller's
periodic `after()` tick — not in a separate thread. Each tick the
controller drains every available snapshot from the queue and calls
`engine.record(snapshot)` once per snapshot (exactly-once processing),
then calls `engine.analyze()` to refresh the result. This keeps the
"latest result" and "latest snapshot" trivially consistent without
cross-thread synchronization, and guarantees analytics work happens on the
only thread allowed to touch Tkinter. **The collector is the only
background thread.**

```python
# inside ApplicationController.poll(), on the GUI main thread:
while True:
    try:
        snap = queue.get_nowait()
    except queue.Empty:
        break
    engine.record(snap)        # exactly once per snapshot
result = engine.analyze()      # refreshed every tick
```

`AnalyticsEngine` therefore does **not** need a `run(input_queue,
stop_event)` method; the controller drives it synchronously.

---

## Member 3 — GUI

**Package:** `gui/`
**Files to implement:** `gui/__init__.py`, `gui/dashboard.py`,
`gui/process_table.py`

### `gui.dashboard`

| | |
| --- | --- |
| **Purpose** | Build and drive the Tkinter root window. Owns all Tkinter calls; no other module imports `tkinter`. |
| **Class** | `Dashboard(config: AppConfig, *, on_close: Callable[[], None] \| None = None)` |
| **Methods** | `update(snapshot: SystemSnapshot, result: AnalyticsResult, figures: Optional[dict[str, "matplotlib.figure.Figure"]] = None) -> None` — redraw gauges + process table, and embed/refresh whichever Matplotlib figures are present in `figures`. `schedule(callback: Callable[[], None], delay_ms: int) -> None` — wraps `root.after(delay_ms, callback)`; the controller's periodic tick is driven through this. `run() -> None` — enters `mainloop()`. `close() -> None` — destroys the window and releases Matplotlib resources. |
| **Input** | Latest `SystemSnapshot` + `AnalyticsResult` + optional `figures` dict, passed in by the controller on each tick. The `figures` dict keys are `"cpu"`, `"memory"`, `"top"`. Missing keys (or `figures=None` when visualization is unavailable) leave that slot unchanged — graceful degradation. `on_close` is wired by the controller to its `stop()` method; the dashboard calls it from its `WM_DELETE_WINDOW` handler. Configuration from `config` (refresh interval, thresholds, memory display unit). |
| **Output** | Renders the window; embeds Matplotlib figures supplied by the controller (built from M4's plot functions) via `matplotlib.backends.backend_tkagg.FigureCanvasTkAgg`. The controller owns the `after()` cadence through `schedule()`; the dashboard must **not** start its own polling loop. |
| **Error behavior** | A `None` field renders as "—" (use `config.format_memory`). An exception inside `update` is caught by the controller at the `after()` boundary, logged, and the next tick proceeds. The window never closes itself on a data error; only `on_close` / `close()` do. |

### `gui.process_table`

| | |
| --- | --- |
| **Purpose** | The scrollable process list widget. |
| **Class** | `ProcessTable(parent: tkinter.Widget, config: AppConfig)` |
| **Methods** | `update(processes: list[ProcessInfo]) -> None` (rebuild rows in place from `snapshot.processes`); `clear() -> None`. |
| **Columns** | PID, Name, CPU%, MEM%, User, State — matching `models.ProcessInfo` fields exactly. |
| **Error behavior** | Empty list → a single placeholder row "No processes". `None` fields render as "—". |

Example contract (the controller constructs and drives the dashboard; Member
3 only implements the class):

```python
import config
from gui.dashboard import Dashboard
from models import SystemSnapshot, AnalyticsResult

cfg = config.DEFAULT_CONFIG
# The controller builds this and wires on_close to its own stop():
dash = Dashboard(cfg, on_close=controller.stop)
# The controller calls, on each GUI tick (main thread):
dash.update(snapshot, result, figures={"cpu": fig_cpu, "memory": fig_mem,
                                        "top": fig_top})
# The controller drives cadence via:
dash.schedule(controller._tick, delay_ms)
# and enters the loop via:
dash.run()   # controller.run() calls this
```

> **Tkinter threading rule:** `Dashboard.update`, the figure embedding
> inside it, and `ProcessTable.update` are called only from the main
> thread, inside the controller's periodic `after()` tick. The collector
> (background thread) never touches the dashboard; it only pushes
> `SystemSnapshot` objects into the queue. This is verified by
> `tests/test_controller.py::test_gui_updates_never_from_background_thread`.

---

## Member 4 — Visualization

**Package:** `visualization/`
**Files to implement:** `visualization/__init__.py`, `visualization/plots.py`

### `visualization.plots`

Pure functions: history in, Matplotlib `Figure` out. No Tkinter imports,
no side effects, no I/O. The controller calls these on the GUI main thread
each tick and hands the resulting figures to `Dashboard.update`.

| Function | Input | Output |
| --- | --- | --- |
| `plot_cpu_history(history: collections.deque[SystemSnapshot] \| list[SystemSnapshot]) -> matplotlib.figure.Figure` | snapshots with `cpu.usage_percent` | Figure with CPU% over time, threshold line at `config.cpu_threshold_percent` |
| `plot_memory_history(history) -> Figure` | snapshots with `memory.usage_percent` | Figure with RAM% (and swap% if present) over time |
| `plot_top_processes(processes: list[ProcessInfo], *, sort_by: str = "cpu") -> Figure` | a process list | horizontal bar chart of top N by `cpu_percent` or `memory_percent` |
| `empty_figure(message: str = "No data") -> Figure` | — | placeholder figure |

| | |
| --- | --- |
| **Error behavior** | Empty / all-`None` history → `empty_figure(...)`, never raises. Missing swap → that line is simply omitted. The controller also wraps each call in its own try/except, so one failing plot does not lose the others. |
| **Units** | X axis is seconds relative to the newest sample (or epoch); Y axis is percent 0-100 for CPU/memory, bytes→display unit via `config.convert_bytes` where absolute memory is shown. Use `config.memory_display_unit` for labels. |
| **Threading** | Called from the GUI main thread by the controller. Must not mutate the input deque (the controller passes `list(history)`). |

Example contract:

```python
import config
from visualization.plots import plot_cpu_history, plot_top_processes
from analytics.engine import AnalyticsEngine

cfg = config.DEFAULT_CONFIG
engine = AnalyticsEngine(cfg)
fig = plot_cpu_history(engine.history())
fig_top = plot_top_processes(engine.history()[-1].processes, sort_by="cpu")
# The controller passes these to dashboard.update(figures={...}).
```

---

## Member 5 — Controller (`main.py`)

**Owner:** Member 5. **Implemented in Stage 2.**

`main.py` provides the orchestration that wires Members 1-4 together. It
is the only place that imports the real member modules, and it does so
lazily inside `build_application` so that merely importing `main` never
fails when a member module is not yet delivered.

### `main.ApplicationController`

Pure orchestration; every collaborator is injected via a factory callable,
so it is fully testable with doubles.

| | |
| --- | --- |
| **Constructor** | `ApplicationController(cfg, *, collector_factory, analytics_factory, dashboard_factory, visualization=None, snapshot_queue=None, stop_event=None, logger=...)` |
| **Factories** | `collector_factory(cfg, queue, stop_event) -> collector`; `analytics_factory(cfg) -> engine`; `dashboard_factory(cfg, on_close) -> dashboard`. `visualization` is a module/object exposing the `plot_*` functions, or `None` for graceful degradation. |
| **Owns** | The `queue.Queue(maxsize=cfg.queue_capacity)`, the `threading.Event` stop event, the latest snapshot/result state, and the periodic GUI tick. |
| **Methods** | `start()` — starts the collector and schedules the first tick; `run()` — `start()` then `dashboard.run()` (blocks until window close), then `shutdown()` in a `finally`; `poll()` — one iteration (drain queue → record/analyze → render), exposed for tests and step driving; `stop()` — idempotent, sets the stop event; `shutdown(timeout=None)` — stop, join collector, close dashboard. |
| **Tick** | Runs on the GUI main thread via `dashboard.schedule(self._tick, delay_ms)`. Drains the queue with `get_nowait` (each snapshot recorded exactly once), calls `analytics.analyze()`, builds figures from `analytics.history()`, and calls `dashboard.update(snapshot, result, figures)`. Reschedules itself unless shut down. |
| **Error handling** | Collector `start()` failure → logged, GUI continues with placeholders. Collector pushing `SystemSnapshot.empty()` → processed normally. `analytics.record`/`analyze` failure → logged, empty result used. `dashboard.update` failure → logged, suppressed. One plot failing → other figures still built. No single failure crashes the dashboard. |
| **Stale policy** | If no fresh snapshot arrives for `max(3 × sampling_interval, 5s)`, a WARNING is logged **once per stale episode** (not every tick) and reset on the next fresh sample; the last known snapshot stays on screen so the dashboard never goes blank. |
| **Backlog** | If a single tick drains more than half the queue capacity, a WARNING is logged (the consumer is behind and the producer is dropping samples). |

### `main.build_application`

| | |
| --- | --- |
| **Signature** | `build_application(cfg=None, *, mock=False, collector_factory=None, analytics_factory=None, dashboard_factory=None, visualization=_UNSET) -> ApplicationController` |
| **Real mode** | Imports `collector.top_collector.TopCollector`, `analytics.engine.AnalyticsEngine`, `gui.dashboard.Dashboard`, and `visualization.plots` lazily. A missing **mandatory** module raises `main.ApplicationError` with an actionable message naming the module, the import error, and the file the owning member must deliver. |
| **Mock mode** | `mock=True` swaps `TopCollector` for `mock_source.MockCollector` (clearly-artificial data; never used in real mode, logged at startup). Analytics/dashboard are still the real modules. |
| **Visualization** | Optional: if `visualization.plots` cannot be imported, a WARNING is logged and the controller starts without charts (graceful degradation). Pass `visualization=None` to disable explicitly, or an object to inject a double. |
| **DI override** | Any `*_factory` argument bypasses the corresponding real import — this is how tests inject doubles and how the controller is assembled before the member modules exist. |

### CLI

```
python main.py                # real monitoring
python main.py --mock         # synthetic data (demo/test)
python main.py --log-level DEBUG
python main.py --env          # apply LINUXPULSE_* config overrides
```

Exit code 2 means a mandatory module could not be loaded (actionable
message on stderr). Logging defaults to INFO so continuous debug output is
not written to the terminal.

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
5. **M5 `main.py` controller** + `tests/test_controller.py` — wires
   threads, queue, lifecycle; smoke test via `python main.py --mock` once
   the GUI is in place. The controller and its tests are delivered in
   Stage 2 with full DI, so they run today against mock doubles even
   before Members 1-4 implement.

Each step must pass `make test` (Stage 2 deliverable) before the next
begins. See [`development_workflow.md`](./development_workflow.md) for
branch and PR rules.
