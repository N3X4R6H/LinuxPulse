"""Integration tests: real analytics engine, real adapters, real gui.ViewState types.

Only the mock provider (main.DemoCollector) replaces live measurements and no Tk
window is created, so these run headless. Pipeline under test:

    DemoCollector -> validate -> to_snapshot -> AnalyticsEngine -> to_view_state -> queue -> (GUI)

`main` is loaded here under its own module name so that the fake teammate modules
injected by tests/test_controller.py can never leak into this file.
"""
import contextlib
import importlib.util
import io
import os
import queue
import sys
import time
import unittest
from dataclasses import replace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    spec = importlib.util.spec_from_file_location("main_integration", os.path.join(ROOT, "main.py"))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)              # needs tkinter + matplotlib (real gui.dashboard import)
    IMPORT_ERROR = None
except SystemExit as exc:                       # main.py exits with a message if tkinter/matplotlib is missing
    app, IMPORT_ERROR = None, str(exc)

from config import AppConfig  # noqa: E402


def fast_cfg(interval=0.01, capacity=256):
    return replace(AppConfig(), sampling_interval_seconds=interval, queue_capacity=capacity)


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


def run_pipeline(collect, seconds, cfg=None, drain_queue=True):
    """Run a Controller for `seconds`; return (controller, published items)."""
    cfg = cfg or fast_cfg()
    q = queue.Queue(maxsize=cfg.queue_capacity)
    ctrl = app.Controller(cfg, q, collect)
    ctrl.start()
    time.sleep(seconds)
    ctrl.stop()
    return ctrl, (drain(q) if drain_queue else q)


@unittest.skipIf(app is None, f"main.py not importable here: {IMPORT_ERROR}")
class PipelineTests(unittest.TestCase):

    def test_snapshot_travels_provider_to_controller_to_analytics(self):
        cfg = fast_cfg()
        ctrl = app.Controller(cfg, queue.Queue(maxsize=cfg.queue_capacity), app.DemoCollector(seed=1))
        seen = []
        real_add = ctrl.engine.add_snapshot
        ctrl.engine.add_snapshot = lambda snap: (seen.append(snap), real_add(snap))[1]
        ctrl.start(); time.sleep(0.08); ctrl.stop()
        self.assertGreater(len(seen), 2, "analytics received no snapshots")
        self.assertTrue(all(isinstance(s, app.SystemSnapshot) for s in seen))
        self.assertTrue(all(s.processes for s in seen))

    def test_gui_receives_current_measurements(self):
        _, items = run_pipeline(app.DemoCollector(seed=2), 0.12)
        states = [i for i in items if isinstance(i, app.ViewState)]
        self.assertTrue(states)
        self.assertFalse([i for i in items if isinstance(i, app.SourceError)])
        last = states[-1]
        self.assertIsNotNone(last.cpu)
        self.assertTrue(0 <= last.ram <= 100)
        self.assertIsNotNone(last.swap)
        self.assertEqual(len(last.load), 3)
        self.assertEqual(last.total, len(last.processes))
        self.assertTrue(last.top_processes and last.top_memory_processes)
        self.assertTrue(all(isinstance(p, app.ProcessRow) for p in last.processes))

    def test_visualization_receives_historical_measurements(self):
        ctrl, items = run_pipeline(app.DemoCollector(seed=3), 0.15)
        last = [i for i in items if isinstance(i, app.ViewState)][-1]
        n = len(ctrl.engine.get_history())
        self.assertGreater(n, 3)
        for series in (last.history.t, last.history.cpu, last.history.ram, last.history.swap,
                       last.history.load1, last.history.mem_used):
            self.assertEqual(len(series), n)
        self.assertLessEqual(max(last.history.t), 0.0)           # time axis is relative to "now"
        self.assertEqual(set(last.history.cpu_dims), set(app.CPU_DIMS))

    def test_multiple_snapshots_update_the_application(self):
        _, items = run_pipeline(app.DemoCollector(seed=4), 0.15)
        states = [i for i in items if isinstance(i, app.ViewState)]
        self.assertGreater(len(states), 3)
        stamps = [s.timestamp for s in states]
        self.assertEqual(stamps, sorted(stamps))
        self.assertGreater(len(set(stamps)), 3)
        # (0.01 s test interval -> only a few jiffies per sample, so CPU is coarsely quantised)
        self.assertGreater(len({round(s.cpu, 3) for s in states if s.cpu is not None}), 1)
        self.assertGreater(len({s.ram for s in states}), 3)
        self.assertGreater(len(states[-1].history.cpu), len(states[0].history.cpu))

    def test_history_is_bounded(self):
        cfg = replace(fast_cfg(), history_limit=5)
        ctrl, items = run_pipeline(app.DemoCollector(seed=5), 0.15, cfg)
        self.assertLessEqual(len(ctrl.engine.get_history()), 5)
        self.assertLessEqual(len(ctrl.extras), 5)
        self.assertLessEqual(len(items[-1].history.cpu), 5)

    def test_queue_stays_bounded_and_keeps_newest(self):
        cfg = fast_cfg(interval=0.005, capacity=3)

        class Counting(app.DemoCollector):
            calls = 0

            def __call__(self, previous_cpu=None, interval=1.0):
                Counting.calls += 1
                return super().__call__(previous_cpu, interval)

        q = queue.Queue(maxsize=cfg.queue_capacity)
        ctrl = app.Controller(cfg, q, Counting(seed=6))      # nothing drains q: a stalled GUI
        ctrl.start(); time.sleep(0.25); ctrl.stop()
        self.assertGreater(Counting.calls, 10, "producer should have outrun the capacity")
        self.assertLessEqual(q.qsize(), 3)
        items = drain(q)
        self.assertEqual([i.timestamp for i in items], sorted(i.timestamp for i in items))
        self.assertGreaterEqual(items[-1].timestamp, time.time() - 1)    # newest survived

    def test_shutdown_stops_worker_and_is_idempotent(self):
        cfg = fast_cfg()
        ctrl = app.Controller(cfg, queue.Queue(maxsize=cfg.queue_capacity), app.DemoCollector(seed=7)).start()
        self.assertTrue(ctrl.thread.is_alive())
        ctrl.stop()
        self.assertFalse(ctrl.thread.is_alive())
        ctrl.stop()                                        # second stop must not raise

    def test_shutdown_is_prompt_with_long_interval(self):
        cfg = fast_cfg(interval=30)
        ctrl = app.Controller(cfg, queue.Queue(maxsize=cfg.queue_capacity), app.DemoCollector(seed=8)).start()
        time.sleep(0.05)
        t0 = time.time()
        ctrl.stop()
        self.assertLess(time.time() - t0, 2.0)
        self.assertFalse(ctrl.thread.is_alive())


@unittest.skipIf(app is None, f"main.py not importable here: {IMPORT_ERROR}")
class MockProviderTests(unittest.TestCase):

    def test_processes_are_created_and_terminated(self):
        dc, prev, pid_sets = app.DemoCollector(seed=9), None, []
        for _ in range(200):
            d = dc(prev, 1.0)
            prev = d["cpu_times"]
            pid_sets.append({p["pid"] for p in d["processes"]})
        created = set().union(*pid_sets) - pid_sets[0]
        terminated = pid_sets[0] - pid_sets[-1]
        self.assertTrue(created, "no process was ever created")
        self.assertTrue(terminated, "no process was ever terminated")
        self.assertTrue(all(len(s) >= 20 for s in pid_sets))

    def test_process_consumption_changes_over_time(self):
        dc = app.DemoCollector(seed=10)
        a, b = dc(None, 1.0), dc(None, 1.0)
        cpu = lambda d: {p["pid"]: p["cpu_percent"] for p in d["processes"]}
        mem = lambda d: {p["pid"]: p["memory_percent"] for p in d["processes"]}
        common = cpu(a).keys() & cpu(b).keys()
        self.assertTrue(any(cpu(a)[k] != cpu(b)[k] for k in common))
        self.assertTrue(any(mem(a)[k] != mem(b)[k] for k in common))

    def test_cpu_ram_swap_load_vary_within_range(self):
        dc, prev, cpus, rams, swaps, loads = app.DemoCollector(seed=11), None, [], [], [], []
        for _ in range(100):
            d = dc(prev, 1.0)
            prev = d["cpu_times"]
            if d["cpu_usage"] is not None:
                cpus.append(d["cpu_usage"])
            rams.append(d["memory"]["ram_usage_percent"])
            swaps.append(d["memory"]["swap_usage_percent"])
            loads.append(d["load_average"]["1min"])
        for series in (cpus, rams, swaps, loads):
            self.assertGreater(len(set(series)), 5)
        for series in (cpus, rams, swaps):
            self.assertTrue(all(0 <= v <= 100 for v in series))

    def test_mock_output_passes_the_collector_contract(self):
        app.validate_collector_data(app.DemoCollector(seed=12)(None, 1.0))


@unittest.skipIf(app is None, f"main.py not importable here: {IMPORT_ERROR}")
class CompatibilityTests(unittest.TestCase):

    def test_validators_accept_good_data_and_reject_bad(self):
        good = app.DemoCollector(seed=1)(None, 1.0)
        self.assertIs(app.validate_collector_data(good), good)
        with self.assertRaisesRegex(app.IntegrationError, "expected a dict"):
            app.validate_collector_data([1, 2])
        with self.assertRaisesRegex(app.IntegrationError, "missing key.*memory"):
            app.validate_collector_data({k: v for k, v in good.items() if k != "memory"})
        with self.assertRaisesRegex(app.IntegrationError, "ram_total"):
            app.validate_collector_data(dict(good, memory={}))
        with self.assertRaisesRegex(app.IntegrationError, "processes"):
            app.validate_collector_data(dict(good, processes="nope"))
        with self.assertRaisesRegex(app.IntegrationError, "SystemSnapshot"):
            app.validate_snapshot({"not": "a snapshot"})
        with self.assertRaisesRegex(app.IntegrationError, "analytics returned"):
            app.validate_analytics_result(None)
        with self.assertRaisesRegex(app.IntegrationError, "top_cpu_processes"):
            app.validate_analytics_result({"resources": {}})
        with self.assertRaisesRegex(app.IntegrationError, "ViewState"):
            app.validate_view_state(object())

    def test_bad_collector_becomes_actionable_source_error(self):
        _, items = run_pipeline(lambda prev: "garbage", 0.05)
        errors = [i for i in items if isinstance(i, app.SourceError)]
        self.assertTrue(errors)
        self.assertIn("IntegrationError", errors[0].message)
        self.assertIn("expected a dict", errors[0].message)

    def test_bad_analytics_becomes_actionable_source_error(self):
        cfg = fast_cfg()
        q = queue.Queue(maxsize=cfg.queue_capacity)
        ctrl = app.Controller(cfg, q, app.DemoCollector(seed=1))
        ctrl.engine.add_snapshot = lambda snap: [1, 2, 3]
        ctrl.start(); time.sleep(0.05); ctrl.stop()
        errors = [i for i in drain(q) if isinstance(i, app.SourceError)]
        self.assertTrue(errors)
        self.assertIn("analytics returned list", errors[0].message)

    def test_controller_keeps_sampling_after_a_bad_sample(self):
        base, calls = app.DemoCollector(seed=3), []

        def flaky(prev):
            calls.append(1)
            return "bad" if len(calls) == 2 else base(prev, 0.01)

        _, items = run_pipeline(flaky, 0.12)
        kinds = [type(i).__name__ for i in items]
        self.assertIn("SourceError", kinds)
        self.assertGreater(kinds.count("ViewState"), 2)

    def test_check_interfaces_passes_for_real_modules(self):
        app.check_interfaces(app.DemoCollector())

    def test_check_interfaces_detects_missing_method(self):
        class Broken:
            pass
        with mock.patch.object(app, "AnalyticsEngine", Broken):
            with self.assertRaisesRegex(app.IntegrationError, "add_snapshot"):
                app.check_interfaces()

    def test_check_interfaces_detects_incompatible_dashboard(self):
        class OldDashboard:
            def __init__(self, config, on_close=None, mock=False):
                pass
        with mock.patch.object(app, "Dashboard", OldDashboard):
            with self.assertRaisesRegex(app.IntegrationError, "parameter 'root'"):
                app.check_interfaces()

    def test_check_interfaces_rejects_non_callable_collector(self):
        with self.assertRaisesRegex(app.IntegrationError, "not callable"):
            app.check_interfaces(collect=42)


@unittest.skipIf(app is None, f"main.py not importable here: {IMPORT_ERROR}")
class ModeSelectionTests(unittest.TestCase):
    """Real vs mock: the right provider is chosen, and only mock mode is labelled."""

    def _run_main(self, argv):
        captured = {}

        class FakeController:
            def __init__(self, cfg, updates, collect):
                captured["collect"] = collect

            def start(self):
                return self

            def stop(self):
                pass

        def fake_dashboard(root, updates, on_close=None, source_name=""):
            captured["label"] = source_name

        with mock.patch.object(sys, "argv", ["main.py"] + argv), \
                mock.patch.object(app, "Controller", FakeController), \
                mock.patch.object(app, "Dashboard", fake_dashboard), \
                mock.patch.object(app, "check_interfaces"), \
                mock.patch.object(app, "tk"), contextlib.redirect_stdout(io.StringIO()):
            app.main()
        return captured

    def test_mock_flag_uses_mock_provider_and_labels_it(self):
        got = self._run_main(["--mock"])
        self.assertIsInstance(got["collect"], app.DemoCollector)
        self.assertEqual(got["label"], "DEMO DATA")

    def test_default_uses_real_collector_without_label(self):
        from collector.top_collector import collect_system_data
        got = self._run_main([])
        self.assertIs(got["collect"], collect_system_data)
        self.assertNotIsInstance(got["collect"], app.DemoCollector)
        self.assertEqual(got["label"], "")

    def test_help_exits_zero_and_mentions_mock(self):
        with mock.patch.object(sys, "argv", ["main.py", "--help"]), \
                mock.patch("sys.stdout") as out:
            with self.assertRaises(SystemExit) as cm:
                app.main()
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--mock", "".join(c.args[0] for c in out.write.call_args_list))

    def test_startup_message_states_the_source(self):
        def startup_text(argv):
            buf = io.StringIO()
            with mock.patch.object(sys, "argv", ["main.py"] + argv), \
                    mock.patch.object(app, "Controller"), mock.patch.object(app, "Dashboard"), \
                    mock.patch.object(app, "check_interfaces"), mock.patch.object(app, "tk"), \
                    contextlib.redirect_stdout(buf):
                app.main()
            return buf.getvalue()

        self.assertIn("MOCK", startup_text(["--mock"]))
        self.assertIn("LIVE", startup_text([]))

    def test_incompatible_interface_exits_2(self):
        with mock.patch.object(sys, "argv", ["main.py", "--mock"]), \
                mock.patch.object(app, "check_interfaces", side_effect=app.IntegrationError("boom")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(app.main(), 2)
        self.assertIn("boom", err.getvalue())


@unittest.skipIf(app is None or not sys.platform.startswith("linux"), "needs Linux and importable main")
class RealCollectorTests(unittest.TestCase):
    """Real mode end to end (no mock anywhere): live /proc + top through the same pipeline."""

    def test_real_collector_flows_through_pipeline(self):
        from collector.top_collector import collect_system_data
        _, items = run_pipeline(collect_system_data, 3.0, fast_cfg(interval=0.5))
        errors = [i for i in items if isinstance(i, app.SourceError)]
        self.assertFalse(errors, errors[:1])
        last = [i for i in items if isinstance(i, app.ViewState)][-1]
        self.assertIsNotNone(last.cpu)
        self.assertGreater(last.total, 0)
        self.assertGreater(last.mem_total_gib, 0)


@unittest.skipIf(IMPORT_ERROR, f"main.py not importable: {IMPORT_ERROR}")
class UserResolutionAdapterTests(unittest.TestCase):
    """top truncates user names to 8 chars + '+'; the adapter must still classify them."""

    def setUp(self):
        app._user_cache.clear()

    def test_truncated_name_resolved_when_unique(self):
        import pwd
        fake = [pwd.struct_passwd(("alexander_long", "x", 1000, 1000, "", "/home/a", "/bin/sh"))]
        with mock.patch("pwd.getpwall", return_value=fake):
            self.assertEqual(app.resolve_user("alexande+"), ("alexander_long", False))

    def test_system_accounts_classified_by_uid(self):
        import pwd
        fake = [pwd.struct_passwd(("systemd-resolve", "x", 982, 982, "", "/", "/sbin/nologin")),
                pwd.struct_passwd(("systemd-network", "x", 981, 981, "", "/", "/sbin/nologin"))]
        with mock.patch("pwd.getpwall", return_value=fake):
            full, system = app.resolve_user("systemd+")
        self.assertEqual(full, "systemd+")          # ambiguous -> keep what top printed
        self.assertTrue(system)                     # both are system accounts -> still classified

    def test_ambiguous_mixed_or_unknown_is_none(self):
        import pwd
        fake = [pwd.struct_passwd(("abcdefgh1", "x", 100, 100, "", "/", "/bin/false")),
                pwd.struct_passwd(("abcdefgh2", "x", 2000, 2000, "", "/", "/bin/sh"))]
        with mock.patch("pwd.getpwall", return_value=fake):
            self.assertIsNone(app.resolve_user("abcdefgh+")[1])
        self.assertEqual(app.resolve_user(None), (None, None))


if __name__ == "__main__":
    unittest.main()
