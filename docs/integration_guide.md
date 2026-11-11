# LINUXPULSE — Integration Guide

**Owner:** Member 5 (integration) · **Audience:** Members 1–4
**Status:** Matches `main.py` after Stage 6 (full integration audit, GUI-level integration tests).

`main.py` is the integration layer. It owns the controller thread, the adapters between
module boundaries, the mock provider and the compatibility checks. It does not implement
collection, analytics, GUI or charts; those stay in their own packages.

## Data flow

```
collector.top_collector.collect_system_data(prev_cpu_times)   (M1)  -> dict
  -> validate_collector_data()                                 (M5)  checks the dict contract
  -> to_snapshot()                                             (M5)  -> models.SystemSnapshot
  -> analytics.engine.AnalyticsEngine.add_snapshot()           (M2)  -> dict
  -> validate_analytics_result()                               (M5)
  -> to_view_state()                                           (M5)  -> gui.dashboard.ViewState
  -> queue.Queue(maxsize=cfg.queue_capacity)
  -> gui.dashboard.Dashboard (Tk main thread)                  (M3)  charts: visualization.plots (M4)
```

One background thread (`Controller._run`) does everything left of the queue. The Tk main
thread only reads the queue, so the GUI never blocks on collection.

## Module contracts

| Module | main.py calls | Contract |
| --- | --- | --- |
| Collector (M1) | `collect_system_data(previous_cpu_times)` | dict with `cpu_usage`, `cpu_cores`, `cpu_times` (cumulative counters incl. `total`), `load_average` (`1min/5min/15min`), `memory` (KiB: `ram_total/ram_used/ram_free`, optional swap keys), `processes` (list of dicts: `pid, user, cpu_percent, memory_percent, state, command`) |
| Analytics (M2) | `AnalyticsEngine(history_size, cpu_threshold, ram_threshold, swap_threshold, top_process_limit)`, `.add_snapshot(snapshot)`, `.get_history()` | `add_snapshot` returns a dict with `resources`, `top_cpu_processes`, `top_memory_processes`, `active_alerts` |
| GUI (M3) | `Dashboard(root, updates, on_close=..., source_name=...)` | consumes `ViewState` or `SourceError` objects from `updates` |
| Charts (M4) | imported by the GUI | main.py hands over history through `ViewState.history` |

Units: the collector reports KiB; `to_snapshot()` converts to bytes for `models`; `to_view_state()`
converts to GiB for the GUI. If a module's interface changes, only the adapters in `main.py`
should need updating.

## Compatibility checks

Wrong types or missing methods raise `IntegrationError` with a message naming the contract,
rather than a bare `KeyError` or `AttributeError` deep in a tick.

* **At startup** `check_interfaces()` verifies that `AnalyticsEngine` has `add_snapshot` and
  `get_history`, that `Dashboard(...)` accepts `root, updates, on_close, source_name`, and that the
  collector is callable. On failure `main.py` prints `error: incompatible module interface(s): ...`
  and exits with code **2**.
* **On every sample** the controller runs `validate_collector_data`, `validate_snapshot`,
  `validate_analytics_result` and `validate_view_state`. A violation is published to the GUI as a
  `SourceError("IntegrationError: ...")` (the dashboard shows SOURCE ERROR) and sampling continues
  with the next tick, so one bad sample never kills the app.

## Running

```bash
python main.py                 # real monitoring (live collector)
python main.py --mock          # simulated data (alias: --demo); labelled "DEMO DATA" in the window
python main.py --interval 1    # sampling interval in seconds (minimum 0.5)
python main.py --help
```

On start-up one line is printed, e.g.
`LinuxPulse starting — source: MOCK (simulated data, not real measurements) · interval 2s · history 300 samples · queue 256 · close the window to exit`
(`LIVE (real collector)` in real mode).

## Mock mode

`main.DemoCollector` is the mock provider. It returns exactly the dict the real collector
returns, so the adapters, analytics, GUI and charts run unchanged. It simulates:

* CPU time counters (a slow-reverting busy level with random spikes), so CPU % and the
  user/system/iowait... breakdown are derived the same way as for real data;
* RAM (bounded random walk on 16 GiB) and swap (bounded random walk on 4 GiB);
* load averages that follow CPU load (1/5/15 min smoothing);
* about 60 processes whose CPU and memory change on every sample, and which are **created and
  terminated** over time (the first three behave like permanent init/kernel tasks; the count stays
  between 20 and 120);
* reproducibility: `DemoCollector(seed=N)` gives the same stream every time.

### Real vs. mock separation

* Real mode uses `collector.top_collector.collect_system_data` and never touches the mock.
* Mock mode never calls the real collector.
* Mock mode shows an amber **DEMO DATA** badge in the top bar (`source_name`) and prints MOCK in the
  start-up line. Real mode shows no badge.
* On platforms other than Linux and macOS, `main.py` prints a notice on stderr and falls back to
  mock mode (so the badge is shown).

## Integration testing procedure

Tests live in `tests/`. `main.py` needs `tkinter` and `matplotlib` (it imports the real GUI
module), so run them with the project's virtual environment:

```bash
.venv/bin/python -m unittest discover -s tests          # everything
.venv/bin/python -m unittest tests.test_integration -v  # integration suite only
.venv/bin/python -m unittest tests.test_controller -v   # adapter/controller unit tests (fake teammate modules)
```

| File | What it uses | What it proves |
| --- | --- | --- |
| `tests/test_gui_integration.py` | **Real** Tk window, analytics and Matplotlib; mock and real collectors; skipped without a display | alerts reach the top-bar badge and alert list, the process table mirrors the snapshot, all Matplotlib drawing is on the GUI thread, the real collector never touches the mock (and vice versa), shutdown stops the worker and cancels all `after()` jobs, the queue does not accumulate when the GUI is starved |
| `tests/test_controller.py` | **Fake** collector, analytics and GUI modules injected into `sys.modules` | adapters, `DemoCollector`, controller logic and CLI wiring in isolation |
| `tests/test_integration.py` | **Real** analytics, adapters and `ViewState`; `DemoCollector` as source; no Tk window | the pipeline end to end, headless |

`test_integration.py` verifies:

* a snapshot travels provider → controller → analytics (`SystemSnapshot` instances reach `add_snapshot`);
* the GUI queue receives current measurements as `ViewState` (CPU, RAM, swap, load, process rows,
  top lists) and no `SourceError` on the happy path;
* visualization input (`ViewState.history`) holds a series per metric, all the same length as the
  analytics history, with time relative to "now";
* multiple snapshots update the application (timestamps advance, values change, history grows);
* history and the queue stay bounded (a never-drained queue of capacity 3 stays ≤ 3 and keeps the
  newest state);
* shutdown joins the worker, is idempotent, and is prompt even with a 30 s interval;
* the mock provider creates/terminates processes and varies CPU, RAM, swap, load and per-process use;
* the validators and `check_interfaces()` produce clear errors for wrong types, missing keys, a
  missing `add_snapshot`, and an old-style `Dashboard` signature;
* a bad sample becomes a `SourceError` and the controller keeps sampling;
* `--mock` selects the mock provider and the badge, the default selects the real collector with no
  badge, `--help` works, and an interface failure exits with code 2;
* (Linux only) the real collector runs through the same pipeline for 3 s without errors.

None of these tests needs a display. Launching the window itself (`python main.py --mock`) is a
manual smoke test.

### Adding a test

Use `run_pipeline(collector, seconds, cfg)` in `test_integration.py`: it runs a `Controller` for the
given time, stops it and returns the published items. To simulate a faulty module, pass a callable
returning wrong data, or replace `controller.engine.add_snapshot`.

## Stage 6 integration audit (Member 5)

Audited against `models.py` and this guide, by running the real modules (not only reading them).

### Compatibility findings

| # | Area | Finding | Resolution |
| --- | --- | --- | --- |
| 1 | Class names, imports, signatures | `AnalyticsEngine`, `Dashboard(root, updates, on_close, source_name)`, `collect_system_data(previous_cpu)` all match what `main.py` calls; no import errors; `check_interfaces()` passes. | none needed |
| 2 | Units | Collector: KiB; models: bytes; GUI: GiB; analytics: percent 0-100. Converted only in `to_snapshot` / `to_view_state`. Verified with the real collector (RAM 15.1 GiB, swap 30.2 GiB, percentages consistent). | none needed |
| 3 | Field names | Collector `command`/`user` map to `ProcessInfo.name`/`username`; process dicts from analytics use `name`/`username`. | covered by adapters |
| 4 | **Config default** | `config.py` had CPU alert threshold 90 %, but README/Context specify 80 % (RAM 85, swap 80 agreed). | **Fixed** in `config.py` (M5-owned): 80.0 |
| 5 | **Truncated user names** | `top` prints at most 8 chars plus `+` (`rangero+`, `systemd+`). The old adapter looked up `rangero` and failed, so those accounts were unclassified in the GUI's "System" filter and shown truncated. | **Adapter** `resolve_user()` in `main.py`: prefix match against `pwd`; full name shown when unique; system/non-system set when all matches agree; ambiguous stays `None`/as printed (3 tests) |
| 6 | Docs vs repo | README referenced `scripts/launch.sh` and `docs/presentation.tex` (neither exists); `docs/architecture.md` listed `mock_source.py` (deleted) and skeleton-only modules. | **Fixed** in README / architecture.md |

### Defects and gaps reported to module owners (not changed by M5)

| Owner | Issue | Suggested minimal correction |
| --- | --- | --- |
| M1 collector | No per-core CPU data, so the GUI per-core panel shows "-". `config.py` `top_*` options (`top_binary`, `top_iterations`, `top_show_threads`) are not read by the collector. | Optional: parse `cpu0..cpuN` lines of `/proc/stat` into a `cpu_per_core` key (adapter already has `per_core=None` slot); delete or honour the dead config options. |
| M2 analytics | Every alert has `severity: "critical"`, so the GUI's amber "warning" badge can never light up. The engine's built-in default CPU threshold is 99 (docs/analytics_design.md), unlike the project's 80; harmless because `main.py` always passes the config values. | Optional: severity "warning" at threshold, "critical" at e.g. threshold + 10. |
| M3 GUI | "High GPU" filter always empty (no GPU source, by design). | none |
| M4 plots | Charts use `layout="constrained"`; one `StackedAreaPlot` draw measured at 54 ms, 36 ms after freezing the layout (-33 %). The Overview redraws 3 canvases per tick. `SystemPlotter` is no longer used by any script. | Optional: `figure.set_layout_engine("none")` after the first draw if CPU use matters. |

### Threading, queue and shutdown (measured with real Tk + Matplotlib)

* Threads: `MainThread` (Tk, Matplotlib) + one `linuxpulse-collector` thread; never more (checked every second for 20-30 s runs in both modes).
* All `FigureCanvasTkAgg.draw/draw_idle` calls and `Dashboard._apply` were wrapped and recorded: 0 calls from a non-main thread (also asserted in `test_gui_integration`).
* The collector thread cannot block the GUI: GUI thread only does `get_nowait()`; the controller drops the oldest item when the queue is full. Observed queue size 0-1; a starved GUI keeps `qsize <= capacity`.
* Shutdown: `Dashboard.shutdown()` cancels all `after()` jobs, calls `Controller.stop()` (event + join), then destroys the window. Afterwards only `MainThread` remained, no child `top` process, controller thread dead; second call is a no-op.

### Resource use of LinuxPulse itself (this machine: 8 cores, Python 3.14, Wayland)

| Run | CPU of the LinuxPulse process | RSS | Child processes |
| --- | --- | --- | --- |
| mock, interval 2 s (default), 30 s | 17.0 % of one core | 116-117 MB | 0 |
| real, interval 2 s (default), 30 s | 17.9 % of one core | 118-119 MB | 1 (`top`, short-lived) |
| mock / real, interval 1 s, 20 s | 27 % / 28.5 % | 117-120 MB | 0 / 1 |
| mock, interval 0.5 s (minimum), 190 s | 36.3 % | 116 → 119 MB, flat from ~60 s on (history reached its 300 cap; queue max 1) | 0 |

Nearly all CPU is on the GUI thread (Matplotlib redraws, about 0.05 s per chart per tick, plus view
switching during the probe); the collector thread used < 0.2 s in 30 s. One `top` subprocess per
sample; no per-process polling. Bounded structures: analytics history (`history_limit`, 300),
controller `extras` deque (same maxlen), update queue (`queue_capacity`, 256, drop-oldest). The username
cache grows only with distinct account names.

Reproduce the probe or the tests:

```bash
.venv/bin/python -m unittest tests.test_gui_integration -v   # needs a display
```

