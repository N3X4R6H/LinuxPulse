"""Controller tests for LINUXPULSE (Member 5).

These tests exercise :class:`main.ApplicationController` entirely through
dependency injection: every collaborator (collector, analytics, dashboard,
visualization) is replaced with an in-test double, so the suite runs
without numpy, matplotlib, Tkinter, or any of the member-owned modules
being implemented.

Coverage:

* queue draining and exactly-once processing
* snapshot delivery to the dashboard
* analytics-result delivery
* GUI updates are never invoked from the background thread
* collector failures (empty snapshots + start() raising) do not crash
* analytics failures fall back to an empty result
* mock mode end-to-end with the real :class:`mock_source.MockCollector`
* shutdown: stop event, join, dashboard close, no new cycles, no reschedule
* graceful degradation when visualization is missing or partially failing
* stale-snapshot policy warns once per episode and resets on fresh data
* queue backlog warning
* dependency-injection overrides and ``build_application`` error behavior
* CLI returns a non-zero code when mandatory modules are missing
* no fake measurements are ever substituted when no data is available
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import unittest
from typing import Any, List, Optional

import config
from main import (ApplicationController, ApplicationError, build_application,
                  main as cli_main)
from mock_source import MockCollector
from models import (AnalyticsResult, CPUInfo, LoadAverages, MemoryInfo,
                    ProcessInfo, SwapInfo, SystemSnapshot)


# ---------------------------------------------------------------------- #
# Test doubles
# ---------------------------------------------------------------------- #
class FakeDashboard:
    """Records every interaction so tests can assert on call order, args,
    and the thread each call happened on."""

    def __init__(self, cfg: config.AppConfig, *,
                 on_close: Optional[Any] = None) -> None:
        self.cfg = cfg
        self.on_close = on_close
        self.updates: List[tuple] = []      # (snapshot, result, figures, thread_id)
        self.scheduled: List[tuple] = []    # (callback, delay_ms)
        self.closed = False
        self.run_count = 0

    # Dashboard contract (see docs/integration_guide.md, Member 3).
    def update(self, snapshot, result, figures=None) -> None:
        self.updates.append(
            (snapshot, result, figures, threading.get_ident()))

    def schedule(self, callback, delay_ms) -> None:
        # Do NOT auto-invoke: tests drive ticks via controller.poll().
        self.scheduled.append((callback, delay_ms))

    def run(self) -> None:
        self.run_count += 1

    def close(self) -> None:
        self.closed = True


class FakeAnalytics:
    """Records record() calls and returns a configurable analyze() result."""

    def __init__(self, cfg: config.AppConfig) -> None:
        self.cfg = cfg
        self.recorded: List[SystemSnapshot] = []
        self._history = []  # plain list; exposes history() like the real engine
        self.analyze_count = 0
        self.analyze_raises: Optional[BaseException] = None
        self._next_result: Optional[AnalyticsResult] = None

    def record(self, snapshot: SystemSnapshot) -> None:
        self.recorded.append(snapshot)
        self._history.append(snapshot)

    def analyze(self) -> AnalyticsResult:
        self.analyze_count += 1
        if self.analyze_raises is not None:
            exc = self.analyze_raises
            self.analyze_raises = None  # one-shot
            raise exc
        if self._next_result is not None:
            return self._next_result
        return AnalyticsResult(
            sample_count=len(self._history), generated_at=time.time())

    def history(self):
        return list(self._history)

    def set_result(self, result: AnalyticsResult) -> None:
        self._next_result = result


class FakeCollector:
    """Pushes a configured snapshot sequence from a daemon thread.

    Records the thread id it ran on so tests can prove the dashboard was
    never touched from that thread. ``fail=True`` makes it push
    ``SystemSnapshot.empty()`` for every snapshot, mirroring the real
    collector's error behavior. ``start_raises=True`` makes ``start()``
    raise to exercise graceful degradation.
    """

    def __init__(self, cfg: config.AppConfig, output_queue, stop_event, *,
                 snapshots: Optional[List[SystemSnapshot]] = None,
                 fail: bool = False, interval: float = 0.0,
                 start_raises: bool = False) -> None:
        self.cfg = cfg
        self.queue = output_queue
        self.stop_event = stop_event
        self.snapshots = list(snapshots or [])
        self.fail = fail
        self.interval = interval
        self.start_raises = start_raises
        self._thread: Optional[threading.Thread] = None
        self.thread_id: Optional[int] = None
        self.pushed: List[SystemSnapshot] = []
        self.started = False

    def start(self) -> None:
        if self.start_raises:
            raise RuntimeError("simulated collector start failure")
        self.started = True
        self._thread = threading.Thread(
            target=self._run, name="fake-collector", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.thread_id = threading.get_ident()
        for snap in self.snapshots:
            if self.stop_event.is_set():
                break
            to_push = SystemSnapshot.empty() if self.fail else snap
            self._push(to_push)
            self.pushed.append(to_push)
            if self.interval:
                self.stop_event.wait(self.interval)

    def _push(self, snapshot: SystemSnapshot) -> None:
        try:
            self.queue.put(snapshot, block=False)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(snapshot)
            except queue.Empty:
                pass

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class FakeVisualization:
    """Returns opaque tuple 'figures' so tests need no matplotlib."""

    def __init__(self, *, cpu_raises: bool = False) -> None:
        self.calls: List[tuple] = []
        self.cpu_raises = cpu_raises

    def plot_cpu_history(self, history):
        self.calls.append(("cpu", list(history)))
        if self.cpu_raises:
            raise RuntimeError("cpu plot boom")
        return ("figure", "cpu")

    def plot_memory_history(self, history):
        self.calls.append(("memory", list(history)))
        return ("figure", "memory")

    def plot_top_processes(self, processes, *, sort_by="cpu"):
        self.calls.append(("top", list(processes), sort_by))
        return ("figure", "top")

    def empty_figure(self, message="No data"):
        return ("figure", "empty", message)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _fast_cfg(sampling: float = 0.01) -> config.AppConfig:
    """A config with tiny intervals so tests run in milliseconds."""
    return config.AppConfig(
        sampling_interval_seconds=sampling,
        gui_refresh_interval_seconds=0.01,
        history_limit=50,
        queue_capacity=16,
        shutdown_timeout_seconds=2.0,
    )


def _snap(cpu: float = 10.0) -> SystemSnapshot:
    return SystemSnapshot(
        timestamp=time.time(),
        cpu=CPUInfo(usage_percent=cpu, core_count=4,
                    load_averages=LoadAverages(0.1, 0.2, 0.3)),
        memory=MemoryInfo.from_total_used_free(8 * 1024 ** 3, 4 * 1024 ** 3),
        swap=SwapInfo.from_total_used(2 * 1024 ** 3, 0),
        processes=[ProcessInfo(pid=1, name="init", cpu_percent=0.0,
                               memory_percent=0.1, username="root",
                               state="S")],
    )


_CONTROLLERS: List[ApplicationController] = []


def make_controller(*, cfg: Optional[config.AppConfig] = None,
                    collector_cls=FakeCollector,
                    collector_kwargs: Optional[dict] = None,
                    analytics_cls=FakeAnalytics,
                    dashboard_cls=FakeDashboard,
                    visualization: Any = ...) -> ApplicationController:
    """Build a controller wired to the given double classes.

    The controller's own factory callables construct each collaborator
    with the resources it owns (queue, stop event, on-close callback), so
    the test exercises the real construction path. The built controller is
    registered for tearDown cleanup.
    """
    cfg = cfg if cfg is not None else _fast_cfg()
    ck = collector_kwargs or {}
    viz = None if visualization is ... else visualization
    ctrl = ApplicationController(
        cfg,
        collector_factory=lambda c, q, ev: collector_cls(c, q, ev, **ck),
        analytics_factory=lambda c: analytics_cls(c),
        dashboard_factory=lambda c, on_close: dashboard_cls(c, on_close=on_close),
        visualization=viz,
    )
    _CONTROLLERS.append(ctrl)
    return ctrl


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #
class ControllerTests(unittest.TestCase):

    def tearDown(self) -> None:
        for ctrl in _CONTROLLERS:
            try:
                ctrl.stop()
                if hasattr(ctrl.collector, "join"):
                    ctrl.collector.join(timeout=1.0)
            except Exception:
                pass
        _CONTROLLERS.clear()

    # --- queue behavior -------------------------------------------------
    def test_queue_drains_each_snapshot_exactly_once(self) -> None:
        ctrl = make_controller()
        s1, s2, s3 = _snap(1), _snap(2), _snap(3)
        for s in (s1, s2, s3):
            ctrl.queue.put_nowait(s)
        ctrl.poll()
        self.assertEqual(ctrl.analytics.recorded, [s1, s2, s3])
        # Second poll: queue empty -> no new records (exactly once overall).
        ctrl.poll()
        self.assertEqual(ctrl.analytics.recorded, [s1, s2, s3])
        self.assertEqual(ctrl.analytics.analyze_count, 2)

    def test_queue_backlog_warning_when_consumer_behind(self) -> None:
        ctrl = make_controller(cfg=_fast_cfg())  # queue_capacity=16
        for i in range(10):  # > queue_capacity // 2 == 8
            ctrl.queue.put_nowait(_snap(float(i)))
        with self.assertLogs("linuxpulse", level="WARNING") as cm:
            ctrl.poll()
        self.assertTrue(any("falling behind" in m for m in cm.output))

    # --- snapshot & analytics delivery ----------------------------------
    def test_snapshot_delivered_to_dashboard(self) -> None:
        s = _snap(42.0)
        ctrl = make_controller(collector_kwargs={"snapshots": [s]})
        ctrl.start()
        ctrl.collector.join(timeout=2.0)
        ctrl.poll()
        self.assertTrue(ctrl.dashboard.updates)
        delivered = ctrl.dashboard.updates[-1][0]
        self.assertEqual(delivered, s)

    def test_analytics_result_passed_to_dashboard(self) -> None:
        ctrl = make_controller()
        result = AnalyticsResult(
            sample_count=7, generated_at=time.time(),
            cpu=__import__("models").MetricStatistics(current=55.0))
        ctrl.analytics.set_result(result)
        ctrl.queue.put_nowait(_snap(1))
        ctrl.poll()
        _, delivered_result, _, _ = ctrl.dashboard.updates[-1]
        self.assertEqual(delivered_result, result)

    # --- thread safety --------------------------------------------------
    def test_gui_updates_never_from_background_thread(self) -> None:
        snaps = [_snap(float(i)) for i in range(20)]
        ctrl = make_controller(
            collector_kwargs={"snapshots": snaps, "interval": 0.001})
        ctrl.start()
        # Poll repeatedly while the collector is still pushing.
        for _ in range(10):
            ctrl.poll()
            time.sleep(0.002)
        ctrl.stop()
        ctrl.collector.join(timeout=2.0)
        main_thread = threading.get_ident()
        collector_thread = ctrl.collector.thread_id
        self.assertIsNotNone(collector_thread)
        self.assertNotEqual(main_thread, collector_thread)
        self.assertTrue(ctrl.dashboard.updates)
        update_threads = {tid for (_, _, _, tid) in ctrl.dashboard.updates}
        self.assertEqual(
            update_threads, {main_thread},
            f"dashboard.update was called from threads {update_threads}; "
            f"expected only the main thread {main_thread}")

    # --- collector failures ---------------------------------------------
    def test_collector_failure_pushes_empty_and_does_not_crash(self) -> None:
        ctrl = make_controller(
            collector_kwargs={"snapshots": [_snap(1), _snap(2)],
                              "fail": True})
        ctrl.start()
        ctrl.collector.join(timeout=2.0)
        # A failing collector pushes empty placeholders, never raises.
        self.assertEqual(len(ctrl.collector.pushed), 2)
        self.assertTrue(all(isinstance(s, SystemSnapshot)
                            for s in ctrl.collector.pushed))
        ctrl.poll()  # must not raise
        self.assertTrue(ctrl.dashboard.updates)
        self.assertEqual(len(ctrl.analytics.recorded), 2)

    def test_collector_start_failure_degrades_gracefully(self) -> None:
        ctrl = make_controller(collector_kwargs={"start_raises": True})
        with self.assertLogs("linuxpulse", level="ERROR"):
            ctrl.start()
        # GUI scheduling still happened -> the dashboard would still run.
        self.assertTrue(ctrl.dashboard.scheduled)
        # poll() still renders an empty placeholder, no crash.
        ctrl.poll()
        self.assertTrue(ctrl.dashboard.updates)

    # --- analytics failures ---------------------------------------------
    def test_analytics_failure_falls_back_to_empty_result(self) -> None:
        ctrl = make_controller()
        ctrl.queue.put_nowait(_snap(1))
        ctrl.analytics.analyze_raises = RuntimeError("boom")
        with self.assertLogs("linuxpulse", level="ERROR"):
            ctrl.poll()
        self.assertTrue(ctrl.dashboard.updates)
        _, result, _, _ = ctrl.dashboard.updates[-1]
        self.assertEqual(result.sample_count, 0)  # AnalyticsResult.empty()

    # --- mock mode ------------------------------------------------------
    def test_mock_mode_produces_synthetic_snapshots(self) -> None:
        cfg = _fast_cfg(sampling=0.01)
        ctrl = make_controller(
            cfg=cfg, collector_cls=MockCollector, collector_kwargs={})
        ctrl.start()
        time.sleep(0.05)  # let the mock collector push a few samples
        # Poll while still running: stop() would set _shutdown and make
        # poll() a no-op, so we must drain before stopping.
        ctrl.poll()
        ctrl.stop()
        ctrl.collector.join(timeout=2.0)
        self.assertTrue(ctrl.dashboard.updates)
        snap = ctrl.dashboard.updates[-1][0]
        # Synthetic but real-shaped data, not None placeholders.
        self.assertIsNotNone(snap.cpu.usage_percent)
        self.assertTrue(snap.processes)
        self.assertGreater(snap.memory.total_bytes, 0)

    # --- shutdown -------------------------------------------------------
    def test_shutdown_sets_stop_event_joins_and_closes(self) -> None:
        ctrl = make_controller(collector_kwargs={"snapshots": [_snap(1)]})
        ctrl.start()
        ctrl.shutdown(timeout=2.0)
        self.assertTrue(ctrl.stop_event.is_set())
        self.assertTrue(ctrl._shutdown)
        self.assertTrue(ctrl.dashboard.closed)
        self.assertFalse(ctrl.collector.is_alive())

    def test_poll_after_shutdown_is_noop(self) -> None:
        ctrl = make_controller()
        ctrl.shutdown(timeout=1.0)
        updates_before = len(ctrl.dashboard.updates)
        ctrl.poll()
        self.assertEqual(len(ctrl.dashboard.updates), updates_before)

    def test_tick_does_not_reschedule_after_shutdown(self) -> None:
        ctrl = make_controller()
        ctrl.start()
        scheduled_after_start = len(ctrl.dashboard.scheduled)
        ctrl.shutdown(timeout=1.0)
        ctrl._tick()  # must return without scheduling again
        self.assertEqual(len(ctrl.dashboard.scheduled), scheduled_after_start)

    def test_window_close_callback_triggers_shutdown(self) -> None:
        ctrl = make_controller()
        self.assertIsNotNone(ctrl.dashboard.on_close)
        ctrl.dashboard.on_close()  # simulate the user closing the window
        self.assertTrue(ctrl.stop_event.is_set())
        self.assertTrue(ctrl._shutdown)

    # --- visualization / graceful degradation --------------------------
    def test_missing_visualization_does_not_block_monitoring(self) -> None:
        ctrl = make_controller(visualization=None)
        ctrl.queue.put_nowait(_snap(1))
        ctrl.poll()
        self.assertTrue(ctrl.dashboard.updates)
        _, _, figures, _ = ctrl.dashboard.updates[-1]
        self.assertIsNone(figures)

    def test_visualization_figures_built_and_passed(self) -> None:
        viz = FakeVisualization()
        ctrl = make_controller(visualization=viz)
        ctrl.queue.put_nowait(_snap(1))
        ctrl.poll()
        _, _, figures, _ = ctrl.dashboard.updates[-1]
        self.assertIsInstance(figures, dict)
        self.assertIn("cpu", figures)
        self.assertIn("memory", figures)
        self.assertIn("top", figures)

    def test_visualization_partial_failure_keeps_other_figures(self) -> None:
        viz = FakeVisualization(cpu_raises=True)
        ctrl = make_controller(visualization=viz)
        ctrl.queue.put_nowait(_snap(1))
        with self.assertLogs("linuxpulse", level="DEBUG"):
            ctrl.poll()
        _, _, figures, _ = ctrl.dashboard.updates[-1]
        self.assertIsInstance(figures, dict)
        self.assertNotIn("cpu", figures)   # failed -> omitted
        self.assertIn("memory", figures)   # survived

    # --- stale policy ---------------------------------------------------
    def test_stale_policy_warns_once_then_resets_on_fresh_data(self) -> None:
        ctrl = make_controller(cfg=_fast_cfg(sampling=0.01))
        ctrl.queue.put_nowait(_snap(1))
        ctrl.poll()  # fresh data
        self.assertFalse(ctrl._stale_warned)

        # Wind the clock back so the snapshot is past the stale threshold.
        ctrl._last_received_wall_time = time.time() - (ctrl._stale_threshold + 5)
        with self.assertLogs("linuxpulse", level="WARNING") as cm:
            ctrl.poll()
        self.assertTrue(ctrl._stale_warned)
        stale_warnings = [r for r in cm.records
                          if r.levelno == logging.WARNING
                          and "no fresh samples" in r.getMessage()]
        self.assertEqual(len(stale_warnings), 1)

        # Second stale tick: must NOT warn again (once per episode).
        records: List[logging.LogRecord] = []

        class _CountHandler(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = _CountHandler()
        handler.setLevel(logging.WARNING)
        ctrl._logger.addHandler(handler)
        try:
            ctrl.poll()
        finally:
            ctrl._logger.removeHandler(handler)
        repeat = [r for r in records
                  if r.levelno == logging.WARNING
                  and "no fresh samples" in r.getMessage()]
        self.assertEqual(len(repeat), 0)

        # Fresh data resets the flag.
        ctrl.queue.put_nowait(_snap(2))
        ctrl.poll()
        self.assertFalse(ctrl._stale_warned)

    # --- no fake measurements -------------------------------------------
    def test_no_fake_measurements_when_no_data(self) -> None:
        ctrl = make_controller()
        ctrl.poll()  # nothing was ever collected
        self.assertTrue(ctrl.dashboard.updates)
        snap = ctrl.dashboard.updates[-1][0]
        # An empty placeholder: None fields, never invented numbers.
        self.assertIsNone(snap.cpu.usage_percent)
        self.assertIsNone(snap.memory.usage_percent)
        self.assertEqual(snap.processes, [])

    # --- dependency injection & assembly --------------------------------
    def test_build_application_with_injected_factories(self) -> None:
        cfg = _fast_cfg()
        analytics = FakeAnalytics(cfg)
        dashboard = FakeDashboard(cfg)
        viz = FakeVisualization()
        collector = FakeCollector(
            cfg, queue.Queue(maxsize=cfg.queue_capacity),
            threading.Event(), snapshots=[_snap(1)])
        ctrl = build_application(
            cfg,
            collector_factory=lambda c, q, ev: collector,
            analytics_factory=lambda c: analytics,
            dashboard_factory=lambda c, on_close: dashboard,
            visualization=viz)
        _CONTROLLERS.append(ctrl)
        self.assertIs(ctrl.collector, collector)
        self.assertIs(ctrl.analytics, analytics)
        self.assertIs(ctrl.dashboard, dashboard)
        self.assertIs(ctrl.visualization, viz)

    def test_build_application_mock_uses_mock_collector(self) -> None:
        cfg = _fast_cfg()
        ctrl = build_application(
            cfg, mock=True,
            analytics_factory=lambda c: FakeAnalytics(c),
            dashboard_factory=lambda c, on_close: FakeDashboard(
                c, on_close=on_close))
        _CONTROLLERS.append(ctrl)
        self.assertIsInstance(ctrl.collector, MockCollector)
        self.assertIsInstance(ctrl.analytics, FakeAnalytics)
        self.assertIsInstance(ctrl.dashboard, FakeDashboard)


class BuildApplicationTests(unittest.TestCase):
    """build_application error behavior when real modules are absent."""

    def test_missing_mandatory_raises_actionable_error(self) -> None:
        with self.assertRaises(ApplicationError) as cm:
            build_application(_fast_cfg())
        msg = str(cm.exception)
        self.assertIn("Mandatory module", msg)
        # Names the file the owning member must deliver.
        self.assertTrue(
            "engine.py" in msg or "dashboard.py" in msg
            or "top_collector.py" in msg,
            f"error message is not actionable: {msg}")

    def test_cli_main_returns_nonzero_when_modules_missing(self) -> None:
        # --mock still needs analytics+dashboard, which are absent here.
        rc = cli_main(["--mock", "--log-level", "CRITICAL"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
