# LINUXPULSE — Architecture

**Owner:** Member 5 (architecture, integration, profiling, build, release)
**Status:** Stage 1 architectural foundation + Stage 2 controller wiring
**Last updated:** 2026-11-08

This document is the authoritative description of how LINUXPULSE fits
together. Module owners implement against the contracts described here and
in [`integration_guide.md`](./integration_guide.md); the data shapes they
exchange are defined in [`../models.py`](../models.py) and the tunable
parameters in [`../config.py`](../config.py).

---

## 1. Overall architecture

LINUXPULSE is a real-time Linux monitoring dashboard. It samples system
metrics by driving `top` in batch mode through a subprocess, parses the
output into typed snapshots, keeps a bounded history, derives analytics
over that history, and renders a Tkinter dashboard with Matplotlib
visualizations. The design is a classic producer/consumer pipeline with a
bounded queue between the producer (collector) and the consumers
(analytics engine and GUI).

The system is organised in four layers, each owned by a single member:

```
                 +-----------------+
                 |   main.py (M5)  |   entry point: wiring + lifecycle
                 +--------+--------+
                          |
            +-------------+-------------+
            |                           |
   +--------v--------+        +--------v--------+
   | collector (M1)  |        |    GUI (M3)     |
   | top -> snapshot |        | Tkinter window  |
   +--------+--------+        | + process table |
            |                 +--------+--------+
            |  SystemSnapshot          ^
            v                          |  AnalyticsResult / SystemSnapshot
   +----------------+   snapshots      |
   | bounded queue  | <--------------> +--------v--------+
   +--------+-------+                  | analytics (M2)  |
            |                          | engine + alerts |
            | history (deque)          +--------+--------+
            v                                   ^
   +----------+---------+    snapshots/history  |
   | visualization (M4) | <---------------------+
   | Matplotlib figures |
   +--------------------+
```

Layer responsibilities:

| Layer | Owner | Responsibility |
| --- | --- | --- |
| Entry / lifecycle | M5 | `main.py` wires components, owns threads, shutdown |
| Collector | M1 | Drive `top`, parse output into `SystemSnapshot` |
| Analytics | M2 | Reduce history into `AnalyticsResult`, raise `AlertInfo` |
| GUI | M3 | Tkinter dashboard, process table, schedule refresh |
| Visualization | M4 | Matplotlib figures from history/analytics |
| Shared infra | M5 | `config.py`, `models.py`, build, docs, profiling |

`config.py` and `models.py` are the shared spine: every layer reads its
parameters from `config.DEFAULT_CONFIG` and exchanges only the dataclasses
defined in `models`. No layer invents its own configuration literal or its
own ad-hoc dict shape.

## 2. Module ownership

| Path | Owner | Stage-2 artefact |
| --- | --- | --- |
| `main.py` | M5 | **delivered** (controller + DI + CLI) |
| ~~`mock_source.py`~~ | M5 | removed; the mock provider is `main.DemoCollector` |
| `tests/test_controller.py` | M5 | **delivered** (22 tests) |
| `config.py` | M5 | **delivered** |
| `models.py` | M5 | **delivered** |
| `requirements.txt` | M1 + M5 | **delivered** |
| `Makefile` | M5 | **delivered** (Stage 4) |
| `README.md` | M3 + M5 | **delivered** |
| `.gitignore` | M5 | **delivered** |
| `collector/` | M1 | **delivered** (integrated, Stage 6) |
| `analytics/` | M2 | **delivered** (integrated, Stage 6) |
| `gui/` | M3 | **delivered** (integrated, Stage 6) |
| `visualization/` | M4 | **delivered** (integrated, Stage 6) |
| `scripts/launch.sh` | M1 | not yet |
| `scripts/profile.sh` | M5 | **delivered** (Stage 5) |
| `tests/` | M1, M2, M4, M5 | **delivered** |
| `profiling/` | M5 + M2 | **delivered** (Stage 5) |
| `docs/architecture.md` | M5 | **delivered** |
| `docs/integration_guide.md` | M5 | **delivered** |
| `docs/development_workflow.md` | M5 | **delivered** |

The package `__init__.py` files in `collector/`, `analytics/`, `gui/`,
`visualization/` and `tests/` were created by M5 as empty placeholders so
the import graph resolves during integration; each module's owner fills in
their own `__init__.py` content.

## 3. Data flow

1. **Sample.** The collector thread invokes `top -b -n 1 -H` (flags from
   `config`) every `sampling_interval_seconds` (default 2 s).
2. **Parse.** `collector.parser` converts the raw text into a
   `models.SystemSnapshot`. Memory is stored in bytes; percentages in
   0-100. Unavailable fields are `None`, never `0`.
3. **Enqueue.** The collector pushes the snapshot onto a bounded
   `queue.Queue` (capacity `config.queue_capacity`, default 256). If the
   queue is full the **oldest pending** snapshot is dropped, on the
   principle that freshest data matters most and a backlog means the
   consumer is already overloaded.
4. **Drain + history.** The controller's periodic tick (on the GUI main
   thread, see §4) pulls every available snapshot off the queue with
   `get_nowait` — each snapshot is recorded exactly once — and appends it
   to the analytics engine's `collections.deque(maxlen=history_limit)`
   (default 300 samples ≈ 10 minutes). The deque silently evicts the
   oldest entry when full — this is the only place history is trimmed.
5. **Analyze.** On the same tick the controller calls
   `analytics.analyze()` to reduce the deque into a
   `models.AnalyticsResult` (statistics, trend slopes, top processes,
   alerts) using thresholds from `config`.
6. **Render.** On the same tick the controller builds Matplotlib figures
   from the deque via the visualization functions and calls
   `dashboard.update(snapshot, result, figures)`. The dashboard embeds
   them via `FigureCanvasTkAgg`. All three steps (drain, analyze, render)
   happen on the GUI main thread inside one `after()` callback.

No data flows the other direction. The GUI never calls the collector
directly; it reads published results. This keeps the pipeline
single-direction and the collector free of UI concerns.

## 4. Threading architecture

**One background thread** plus the Tkinter main loop. (Stage 1 sketched a
separate analytics thread; Stage 2 simplifies this — analytics runs on the
GUI main thread, see below.)

| Thread | Owner | Daemon | Role |
| --- | --- | --- | --- |
| `linuxpulse-collector` | M1 | yes | subprocess + parse + enqueue |
| `linuxpulse-gui` (main) | M5 controller + M3 dashboard | no (main) | drain queue → analytics → figures → dashboard, via `after()` |

The collector is a daemon (`config.collector_thread_daemon`) so that
closing the GUI window can terminate the process even if a join times out.
The GUI and all analytics/visualization work run on the process main
thread because Tkinter is not thread-safe and must be driven from the
thread that created the root window.

Why analytics is on the main thread, not its own thread: the analytics
engine's work (drain + record + analyze) is cheap relative to a GUI
refresh, and running it on the same thread that renders eliminates the
need to synchronize a "latest result" between an analytics thread and the
GUI thread. The only cross-thread boundary is the queue.

Cross-thread data hand-off uses exactly one synchronization point:

* A bounded `queue.Queue` between the collector (producer) and the
  controller's tick on the GUI thread (consumer). Thread-safe by design.

The latest snapshot/result pair, the history deque, and all Matplotlib
figures are touched only by the GUI main thread, so they need no lock for
the data flow. The controller keeps a `threading.Lock` around its
`latest_snapshot`/`latest_result` fields purely as defensive hygiene for
the public `latest_snapshot` / `latest_result` properties; it is not on
the hot path.

`time.sleep` is never used to pace the GUI. The controller schedules its
next tick through `dashboard.schedule(callback, delay_ms)` (which wraps
`root.after(int(gui_refresh_interval_seconds * 1000), ...)`), keeping the
Tkinter event loop responsive.

## 5. GUI update strategy

The application follows a strict "main thread touches widgets" rule:

* The collector (background thread) only pushes `SystemSnapshot` objects
  into the queue; it **never** calls any Tkinter or Matplotlib method.
* On each `after()` tick the controller, on the GUI main thread:
  1. Drains every available snapshot from the queue, recording each into
     analytics exactly once.
  2. Calls `analytics.analyze()` to refresh the `AnalyticsResult`.
  3. Builds Matplotlib figures from `analytics.history()` via the
     visualization functions (each wrapped in its own try/except so one
     failure does not lose the others).
  4. Calls `dashboard.update(snapshot, result, figures)` — the dashboard
     redraws gauges, the process table, and embeds the figures.
* If no snapshot is available yet, the controller passes
  `SystemSnapshot.empty()` so the dashboard renders "—" placeholders
  rather than blank cells. If no fresh sample arrives for the stale
  threshold (`max(3 × sampling_interval, 5s)`), a warning is logged once
  per stale episode; the last known snapshot stays on screen.
* `dashboard.update` exceptions are caught at the `after()` boundary,
  logged, and the next tick proceeds — the window never closes itself on
  a data error.

Widgets are updated in place where possible (table cell text) rather than
destroyed and recreated, to avoid flicker and keep memory stable over long
runs.

## 6. Historical data management

* Storage: a single `collections.deque(maxlen=history_limit)` held by the
  analytics engine, appended by the controller on the GUI main thread.
  Default 300 samples.
* Retention: automatic, O(1) eviction of the oldest sample on append. No
  manual pruning loop, no periodic cleanup thread.
* Window: at 2 s × 300 samples the window is 600 s (10 min). The
  visualization plots this full window; analytics statistics are computed
  over the same window unless a shorter window is requested.
* Memory budget: one `SystemSnapshot` with 20 processes is on the order of
  a few KiB; 300 of them is well under a MiB, so in-memory history is
  bounded and cheap. No on-disk persistence is planned for Stage 1.
* Persistence to disk (CSV/SQLite) is out of scope for Stage 1 and would
  be added behind the same `SystemSnapshot` interface if needed later.

## 7. Error handling

The guiding rule is **the GUI must keep running**. No data error from a
sub-layer may crash the dashboard.

| Failure | Handling |
| --- | --- |
| `top` binary missing / non-zero exit | Collector logs the error and emits `SystemSnapshot.empty()` for that tick; analytics sees an empty snapshot and reports `None` statistics; GUI shows "—". |
| `top` output malformed / a field unparsable | Parser fills the offending field with `None` and keeps the rest of the snapshot; it never raises on a partial parse. Only a fully unparseable blob raises `ParseError`, which the collector catches and converts to an empty snapshot. |
| Queue full | Collector drops the oldest pending snapshot (see §3) and continues; no blocking, no back-pressure onto `top`. |
| Analytics receives empty / all-`None` history | Returns `AnalyticsResult.empty()`; never divides by zero (percentages are `None` when `total == 0`). |
| Visualization receives empty history | Returns a placeholder figure with an explanatory label rather than an empty axes. |
| Tkinter exception in a refresh callback | Caught at the `after()` boundary, logged, and the next tick proceeds. |

All exceptions are logged to `stderr` with the thread name and timestamp.
No layer silently swallows an exception without at least a log line.

## 8. Shutdown lifecycle

Shutdown is triggered by the GUI window close (the only intended exit
path) or by `KeyboardInterrupt` / `SIGTERM` in `main.py`.

1. `main.py` sets a `threading.Event` (`stop_event`) shared with both
   worker threads.
2. The collector stops spawning `top`, terminates any running subprocess
   (`top_terminate_timeout_seconds`), and exits its loop.
3. The analytics thread drains the queue once more, finishes the current
   `analyze` call, and exits.
4. `main.py` joins both threads with `shutdown_timeout_seconds` (default
   5 s). Daemon threads are joined best-effort; if a join times out the
   process still exits because they are daemons.
5. The GUI root window is destroyed and `mainloop()` returns.
6. Matplotlib figures are closed (`plt.close('all')`) to release file
   handles.

The order is deliberate: stop the producer first so the queue can drain,
then the consumer, then the UI. This avoids a final-frame torn write and
guarantees no subprocess is orphaned.
