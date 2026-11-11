"""End-to-end tests through the REAL Tk window, analytics and Matplotlib (Stage 6).

Needs a display; every test is skipped when Tk cannot open one (CI without X/Wayland).
Run:  .venv/bin/python -m unittest tests.test_gui_integration -v
"""
import importlib.util
import os
import queue
import sys
import threading
import time
import unittest
from dataclasses import replace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SKIP = None
try:
    import tkinter as tk
    spec = importlib.util.spec_from_file_location("main_gui_integration", os.path.join(ROOT, "main.py"))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import gui.dashboard as gd
    probe = tk.Tk()
    probe.destroy()
except SystemExit as exc:
    SKIP = str(exc)
except Exception as exc:                      # no display, missing tk/matplotlib ...
    SKIP = f"{type(exc).__name__}: {exc}"

from config import AppConfig  # noqa: E402


def pump(root, seconds, until=None):
    """Run the Tk event loop by hand for up to `seconds` (or until `until()` is true)."""
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if until and until():
            return True
        time.sleep(0.02)
    return bool(until and until())


@unittest.skipIf(SKIP, f"GUI integration needs a display + tkinter/matplotlib ({SKIP})")
class GuiPipelineTests(unittest.TestCase):
    def build(self, collect, demo, **cfg_over):
        cfg = replace(AppConfig(), sampling_interval_seconds=0.3, queue_capacity=8, **cfg_over)
        self.updates = queue.Queue(maxsize=cfg.queue_capacity)
        self.ctrl = app.Controller(cfg, self.updates, collect).start()
        self.root = tk.Tk()
        self.main_thread = threading.current_thread()
        self.bad_thread = []
        for name in ("draw", "draw_idle"):
            orig = getattr(FigureCanvasTkAgg, name)
            def wrapped(s, *a, _o=orig, _n=name, **k):
                if threading.current_thread() is not self.main_thread:
                    self.bad_thread.append(_n)
                return _o(s, *a, **k)
            p = mock.patch.object(FigureCanvasTkAgg, name, wrapped)
            p.start()
            self.addCleanup(p.stop)
        self.dash = gd.Dashboard(self.root, self.updates, on_close=self.ctrl.stop,
                                 source_name="DEMO DATA" if demo else "")
        self.addCleanup(self._cleanup)
        return cfg

    def _cleanup(self):
        if not getattr(self.dash, "_closing", False):
            self.dash.shutdown()

    def test_mock_mode_end_to_end(self):
        # Low thresholds so alerts are certain to be active.
        self.build(app.DemoCollector(seed=1), demo=True, ram_threshold_percent=0.1)
        self.assertTrue(pump(self.root, 8, lambda: self.dash.latest is not None), "no ViewState reached the GUI")
        s = self.dash.latest
        self.assertIsInstance(s, gd.ViewState)
        self.assertEqual(self.dash.status_text, "LIVE")
        # alerts: analytics -> controller -> top-bar badge -> alert list
        self.assertTrue(pump(self.root, 3, lambda: self.dash.topbar.crit.cget("text") not in ("0", "")))
        self.dash.show("processes")
        view = self.dash.views["processes"]
        self.assertTrue(pump(self.root, 3, lambda: len(view.table.tree.get_children()) > 0))
        # process table mirrors the snapshot (all rows, no filter)
        self.assertEqual(len(view.table.tree.get_children()), len(self.dash.latest.processes))
        self.assertTrue(view.alerts.winfo_children())
        self.assertIn("DEMO DATA", [w.cget("text") for w in self._labels(self.dash.topbar)])
        # charts get fed (history reaches the plots) and every view can render the live state
        pump(self.root, 1.5)
        for key in ("overview", "analytics", "processes"):
            self.dash.show(key)
            pump(self.root, 0.6)
        self.assertEqual(self.bad_thread, [], "Matplotlib drawing happened off the GUI thread")
        self.assertLessEqual(self.updates.qsize(), 8)
        self.assertEqual(self.dash.status_text, "LIVE")

    @unittest.skipUnless(sys.platform.startswith("linux"), "real collector is Linux/macOS only")
    def test_real_mode_end_to_end_and_separation(self):
        from collector.top_collector import collect_system_data
        with mock.patch.object(app.DemoCollector, "__call__", side_effect=AssertionError("mock used in real mode")):
            self.build(collect_system_data, demo=False)
            self.assertTrue(pump(self.root, 15, lambda: self.dash.latest is not None))
            pump(self.root, 1.5)
        s = self.dash.latest
        self.assertIsNone(self.dash.error)
        self.assertGreater(len(s.processes), 5)
        self.assertGreater(s.n_cpus, 0)
        self.assertEqual(s.mem_total_gib is not None and s.mem_total_gib > 0, True)
        self.assertNotIn("DEMO DATA", [w.cget("text") for w in self._labels(self.dash.topbar)])
        self.assertEqual(self.bad_thread, [])

    def test_shutdown_stops_worker_and_is_idempotent(self):
        self.build(app.DemoCollector(seed=2), demo=True)
        pump(self.root, 1.0, lambda: self.dash.latest is not None)
        before = threading.active_count()
        self.dash.shutdown()
        self.dash.shutdown()                                    # second call is a no-op
        self.assertFalse(self.ctrl.thread.is_alive())
        self.assertEqual(threading.active_count(), before - 1)
        self.assertEqual(self.dash._jobs, {})                   # all after() jobs cancelled

    def test_queue_never_accumulates_when_gui_is_slow(self):
        cfg = self.build(app.DemoCollector(seed=3), demo=True)
        # starve the GUI: do not pump for a while; the controller keeps publishing
        time.sleep(2.0)
        self.assertLessEqual(self.updates.qsize(), cfg.queue_capacity)
        pump(self.root, 1.0)
        self.assertLessEqual(self.updates.qsize(), 1)

    @staticmethod
    def _labels(widget):
        out = []
        for w in widget.winfo_children():
            if isinstance(w, tk.Label):
                out.append(w)
            out.extend(GuiPipelineTests._labels(w))
        return out


if __name__ == "__main__":
    unittest.main()
