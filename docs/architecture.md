# LINUXPULSE — Architecture

**Owner:** Member 5 (architecture, integration, profiling, build, release)
**Status:** Stage 1 — architectural foundation
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

| Path | Owner | Stage-1 artefact |
| --- | --- | --- |
| `main.py` | M5 | not yet (Stage 2) |
| `config.py` | M5 | **delivered** |
| `models.py` | M5 | **delivered** |
| `requirements.txt` | M1 + M5 | **delivered** |
| `Makefile` | M5 | not yet (Stage 2) |
| `README.md` | M3 + M5 | not yet (Stage 2) |
| `.gitignore` | M5 | **delivered** |
| `collector/` | M1 | package skeleton only |
| `analytics/` | M2 | package skeleton only |
| `gui/` | M3 | package skeleton only |
| `visualization/` | M4 | package skeleton only |
| `scripts/launch.sh` | M1 | not yet |
| `scripts/profile.sh` | M5 | not yet |
| `tests/` | M1, M2, M4 | `__init__.py` only |
| `profiling/` | M5 + M2 | skeleton only |
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
4. **History.** The analytics thread pulls from the queue and appends each
   snapshot to a `collections.deque(maxlen=config.history_limit)` (default
   300 samples ≈ 10 minutes). The deque silently evicts the oldest entry
   when full — this is the only place history is trimmed.
5. **Analyze.** On each tick the analytics engine reduces the deque into a
   `models.AnalyticsResult` (statistics, trend slopes, top processes,
   alerts) using thresholds from `config`.
6. **Render.** The GUI main thread, on a `Tkinter after()` timer
   (`gui_refresh_interval_seconds`, default 1 s), reads the latest
   snapshot + latest `AnalyticsResult` and redraws. Visualization
   functions build Matplotlib figures from the deque; the GUI embeds them
   via `FigureCanvasTkAgg`.

No data flows the other direction. The GUI never calls the collector
directly; it reads published results. This keeps the pipeline
single-direction and the collector free of UI concerns.

## 4. Threading architecture

Three threads plus the Tkinter main loop:

| Thread | Owner | Daemon | Role |
| --- | --- | --- | --- |
| `linuxpulse-collector` | M1 | yes | subprocess + parse + enqueue |
| `linuxpulse-analytics` | M2 | yes | dequeue + history + analyze |
| `linuxpulse-gui` (main) | M3 | no (main) | Tkinter loop, render |

The collector and analytics threads are daemons (`config.*_thread_daemon`)
so that closing the GUI window can terminate the process without an
explicit join succeeding. The GUI runs on the process main thread because
Tkinter is not thread-safe and must be driven from the thread that created
the root window.

Cross-thread data hand-off uses exactly two synchronization points:

* A `queue.Queue` between collector and analytics (thread-safe by design).
* Two single-slot holders — one for the latest `SystemSnapshot`, one for
  the latest `AnalyticsResult` — written by the analytics thread and read
  by the GUI. A single reference assignment is atomic under the GIL, so a
  `threading.Lock` is used only to make the read-modify of "latest pair"
  explicit; it is not contended. The history deque is touched only by the
  analytics thread, so it needs no lock for writes; visualization reads it
  via a shallow copy (`list(history)`) to avoid iteration-during-mutation.

`time.sleep` is never used to pace the GUI. The GUI schedules its next
refresh with `root.after(int(gui_refresh_interval_seconds * 1000), ...)`,
which keeps the Tkinter event loop responsive.

## 5. GUI update strategy

The GUI follows a strict "main thread touches widgets" rule:

* The analytics thread computes results and stashes them; it **never**
  calls any Tkinter method.
* On each `after()` tick the GUI main thread:
  1. Reads the latest snapshot and `AnalyticsResult`.
  2. Updates the process table (rebuild rows from `snapshot.processes`).
  3. Updates headline gauges (CPU%, RAM%, swap%) with thresholds applied
     as colour changes.
  4. Asks the visualization layer to refresh figures and embeds them.
* If no snapshot is available yet, the GUI renders `SystemSnapshot.empty()`
  placeholders ("—" for `None` values) so the window never shows stale or
  blank cells.

Widgets are updated in place where possible (table cell text) rather than
destroyed and recreated, to avoid flicker and keep memory stable over long
runs.

## 6. Historical data management

* Storage: a single `collections.deque(maxlen=history_limit)` held by the
  analytics thread. Default 300 samples.
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
