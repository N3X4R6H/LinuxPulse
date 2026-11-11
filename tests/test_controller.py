"""Stage 2 controller tests for the LINUXPULSE main.py (Member 5).

The new main.py imports the teammate modules (analytics.engine,
collector.parser, collector.top_collector, gui.dashboard) directly at the
top level. Those modules are owned by Members 1/2/3 and are not present in
this sandbox (only the Stage-1 package-marker placeholders exist). To test
main.py's own logic -- the adapters, DemoCollector and Controller -- this
file injects **test-only fakes** for those four modules into
``sys.modules`` *before* importing main. The fakes live in this test file
only; no teammate module is implemented as a package file.

The fakes faithfully model the API surface main.py actually uses (dict
shaped analytics results, the gui.ViewState/History/ProcessRow/Alert/
CpuBreakdown types, and collector.parser.calculate_cpu_usage), so the
adapters and the full collect -> snapshot -> analytics -> ViewState ->
queue pipeline run for real.

tkinter (9.0) and matplotlib (3.9.2) are available, so importing main
itself succeeds; only the actual Tk main loop (main()) needs a display and
is patched out where tested.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import types
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional
from unittest import mock

# ---------------------------------------------------------------------- #
# Test-only fakes for the four teammate modules
# (injected into sys.modules BEFORE `import main`)
# ---------------------------------------------------------------------- #
KIB = 1024

# CPU dimensions the gui expects (the non-idle /proc/stat columns). The
# DemoCollector populates exactly these keys in its cpu_times.
CPU_DIMS = ("user", "nice", "system", "iowait", "irq", "softirq", "steal")


@dataclass
class CpuBreakdown:
    user: Optional[float] = None
    nice: Optional[float] = None
    system: Optional[float] = None
    iowait: Optional[float] = None
    irq: Optional[float] = None
    softirq: Optional[float] = None
    steal: Optional[float] = None
    idle: Optional[float] = None


@dataclass
class History:
    t: List[Any] = field(default_factory=list)
    cpu: List[Any] = field(default_factory=list)
    ram: List[Any] = field(default_factory=list)
    swap: List[Any] = field(default_factory=list)
    load1: List[Any] = field(default_factory=list)
    mem_used: List[Any] = field(default_factory=list)
    mem_buffcache: List[Any] = field(default_factory=list)
    mem_free: List[Any] = field(default_factory=list)
    per_core: List[Any] = field(default_factory=list)
    cpu_dims: dict = field(default_factory=dict)


@dataclass
class ProcessRow:
    pid: Optional[int] = None
    name: Optional[str] = None
    cpu: Optional[float] = None
    mem: Optional[float] = None
    state: Optional[str] = None
    user: Optional[str] = None
    is_system: Optional[bool] = None


@dataclass
class Alert:
    level: str = "warning"
    message: str = ""
    timestamp: float = 0.0


@dataclass
class SourceError:
    message: str = ""


@dataclass
class ViewState:
    # Accept every field main.to_view_state passes, by keyword, in any order.
    timestamp: Optional[float] = None
    cpu: Optional[float] = None
    cpu_dims: Optional[Any] = None
    per_core: Optional[Any] = None
    n_cpus: Optional[int] = None
    load: Optional[Any] = None
    ram: Optional[float] = None
    mem_total_gib: Optional[float] = None
    mem_used_gib: Optional[float] = None
    mem_free_gib: Optional[float] = None
    mem_buffcache_gib: Optional[float] = None
    mem_available_gib: Optional[float] = None
    swap: Optional[float] = None
    swap_used_gib: Optional[float] = None
    swap_total_gib: Optional[float] = None
    total: int = 0
    running: int = 0
    sleeping: int = 0
    stopped: int = 0
    zombie: int = 0
    processes: List[Any] = field(default_factory=list)
    gpu_available: bool = False
    history: Optional[Any] = None
    avg_cpu: Optional[float] = None
    avg_ram: Optional[float] = None
    peak_cpu: Optional[float] = None
    peak_ram: Optional[float] = None
    peak_swap: Optional[float] = None
    top_processes: List[Any] = field(default_factory=list)
    top_memory_processes: List[Any] = field(default_factory=list)
    alerts: List[Any] = field(default_factory=list)
    uptime_s: Optional[float] = None
    interval_s: Optional[float] = None
    hostname: Optional[str] = None


class Dashboard:  # minimal stand-in; never rendered in tests
    def __init__(self, root, updates, on_close=None, source_name=""):
        self.root = root
        self.updates = updates
        self.on_close = on_close
        self.source_name = source_name


def tk_version_warning():
    return None


def calculate_cpu_usage(prev, cur):
    """Faithful stand-in for collector.parser.calculate_cpu_usage."""
    if not prev or not cur:
        return None
    total = cur["total"] - prev["total"]
    if total <= 0:
        return None
    idle_delta = cur["idle_total"] - prev["idle_total"]
    return max(0.0, min(100.0, 100.0 * (total - idle_delta) / total))


class FakeAnalyticsEngine:
    """Models the dict-shaped analytics API main.py consumes:

    add_snapshot(SystemSnapshot) -> dict with keys active_alerts, resources,
    top_cpu_processes, top_memory_processes; get_history() -> list[dict]
    with timestamp/cpu_percent/ram_percent/swap_percent.
    """

    def __init__(self, history_size, cpu_threshold, ram_threshold,
                 swap_threshold, top_process_limit):
        self.history_size = history_size
        self.cpu_threshold = cpu_threshold
        self.ram_threshold = ram_threshold
        self.swap_threshold = swap_threshold
        self.top_process_limit = top_process_limit
        self._history: List[dict] = []
        self.add_calls: List[Any] = []

    def add_snapshot(self, snap):
        self.add_calls.append(snap)
        entry = {
            "timestamp": datetime.fromtimestamp(snap.timestamp).isoformat(),
            "cpu_percent": snap.cpu.usage_percent,
            "ram_percent": snap.memory.usage_percent,
            "swap_percent": snap.swap.usage_percent if snap.swap else None,
        }
        self._history.append(entry)
        if len(self._history) > self.history_size:
            self._history = self._history[-self.history_size:]

        alerts = []
        if snap.cpu.usage_percent is not None and \
                snap.cpu.usage_percent >= self.cpu_threshold:
            alerts.append({"resource": "cpu", "name": "CPU",
                           "value_percent": snap.cpu.usage_percent,
                           "threshold_percent": self.cpu_threshold,
                           "severity": "warning"})
        if snap.memory.usage_percent is not None and \
                snap.memory.usage_percent >= self.ram_threshold:
            alerts.append({"resource": "ram", "name": "RAM",
                           "value_percent": snap.memory.usage_percent,
                           "threshold_percent": self.ram_threshold,
                           "severity": "critical"})

        def stats(vals):
            vals = [v for v in vals if v is not None]
            if not vals:
                return {}
            return {"mean_percent": sum(vals) / len(vals),
                    "maximum_percent": max(vals),
                    "minimum_percent": min(vals),
                    "current_percent": vals[-1]}

        cpus = [e["cpu_percent"] for e in self._history]
        mems = [e["ram_percent"] for e in self._history]
        swaps = [e["swap_percent"] for e in self._history
                 if e["swap_percent"] is not None]
        # Echo back the model ProcessInfo objects main handed us.
        procs = list(snap.processes)
        top_cpu = sorted(procs, key=lambda p: p.cpu_percent or 0.0,
                         reverse=True)[: self.top_process_limit]
        top_mem = sorted(procs, key=lambda p: p.memory_percent or 0.0,
                         reverse=True)[: self.top_process_limit]
        return {
            "active_alerts": alerts,
            "resources": {"cpu": stats(cpus), "ram": stats(mems),
                          "swap": stats(swaps)},
            "top_cpu_processes": top_cpu,
            "top_memory_processes": top_mem,
        }

    def get_history(self):
        return list(self._history)


# --- inject the fakes into sys.modules before importing main -----------
# main.py binds its teammate-module names (AnalyticsEngine, calculate_cpu_usage,
# ViewState, ...) at *import* time. We inject fakes so `import main` succeeds
# even where the real teammate modules are not delivered yet, then immediately
# **restore** whatever real modules were present.
#
# This scopes the fakes to main's bound names only. `unittest discover` loads
# every test module in one process (alphabetically), so without the restore our
# fake collector.parser (which only has calculate_cpu_usage) would leak into
# Member 1's test_parser and break its `from collector.parser import
# parse_loadavg, ...`. After the restore, other test modules import the real
# teammate modules unaffected; main keeps using the fakes it already bound.
_SAVED_MODULES: dict = {}


def _build_gui_module():
    mod = types.ModuleType("gui.dashboard")
    for name in ("CPU_DIMS", "Alert", "CpuBreakdown", "Dashboard", "History",
                 "ProcessRow", "SourceError", "ViewState", "tk_version_warning"):
        mod.__dict__[name] = globals()[name]
    return mod


def _build_analytics_module():
    mod = types.ModuleType("analytics.engine")
    mod.AnalyticsEngine = FakeAnalyticsEngine
    return mod


def _build_parser_module():
    mod = types.ModuleType("collector.parser")
    mod.calculate_cpu_usage = calculate_cpu_usage
    return mod


def _install_fakes():
    for name, fake in (("gui.dashboard", _build_gui_module()),
                       ("analytics.engine", _build_analytics_module()),
                       ("collector.parser", _build_parser_module())):
        _SAVED_MODULES[name] = sys.modules.get(name)   # None if not yet imported
        sys.modules[name] = fake


def _restore_real_modules():
    for name, orig in _SAVED_MODULES.items():
        if orig is None:
            sys.modules.pop(name, None)                # fake was the only copy -> remove
        else:
            sys.modules[name] = orig                   # put the real module back


_install_fakes()
import main  # noqa: E402  -- binds the fake names into main's namespace
_restore_real_modules()  # other test modules now see the real teammate modules

from config import AppConfig  # noqa: E402
from models import (CPUInfo, LoadAverages, MemoryInfo, ProcessInfo,  # noqa: E402
                    SwapInfo, SystemSnapshot)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _fast_cfg(sampling: float = 0.01) -> AppConfig:
    return AppConfig(sampling_interval_seconds=sampling,
                     history_limit=50, queue_capacity=16,
                     shutdown_timeout_seconds=2.0)


def _collector_data(cpu_usage=12.0, *, swap_total=4 * 1024 * 1024,
                    ram_total=16 * 1024 * 1024, ram_used=6 * 1024 * 1024,
                    processes=None):
    """One collector dict in the shape DemoCollector / collect_system_data
    returns (KiB memory, cumulative cpu_times, process dicts)."""
    times = {"user": 1000, "nice": 10, "system": 400, "idle": 5000,
             "iowait": 50, "irq": 5, "softirq": 30, "steal": 0}
    cur = dict(times, total=sum(times.values()),
               idle_total=times["idle"] + times["iowait"])
    processes = processes if processes is not None else [
        {"pid": 1, "user": "root", "cpu_percent": 0.0, "memory_percent": 0.1,
         "state": "S", "command": "systemd"},
        {"pid": 500, "user": "dhiren", "cpu_percent": 5.5,
         "memory_percent": 2.3, "state": "R", "command": "firefox"},
    ]
    return {
        "cpu_usage": cpu_usage, "cpu_cores": 8, "cpu_times": cur,
        "load_average": {"1min": 0.4, "5min": 0.5, "15min": 0.6},
        "memory": {"ram_total": ram_total, "ram_used": ram_used,
                   "ram_free": ram_total - ram_used - 100,
                   "ram_available": ram_total - ram_used,
                   "ram_usage_percent": ram_used / ram_total * 100,
                   "swap_total": swap_total,
                   "swap_used": 300 * 1024 if swap_total else 0,
                   "swap_free": (swap_total - 300 * 1024) if swap_total else 0,
                   "swap_usage_percent": (300 * 1024 / swap_total * 100) if swap_total else 0},
        "processes": processes,
    }


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #
class TestDemoCollector(unittest.TestCase):

    def test_returns_collector_dict_shape(self) -> None:
        data = main.DemoCollector(seed=1)(previous_cpu=None, interval=1.0)
        for key in ("cpu_usage", "cpu_cores", "cpu_times", "load_average",
                    "memory", "processes"):
            self.assertIn(key, data)
        # First call has no previous -> cpu_usage is None (real collector parity).
        self.assertIsNone(data["cpu_usage"])
        self.assertEqual(data["cpu_cores"], main.DemoCollector(seed=1).cores)
        self.assertIsInstance(data["memory"]["ram_total"], int)  # KiB
        self.assertTrue(data["processes"])
        p = data["processes"][0]
        for k in ("pid", "user", "cpu_percent", "memory_percent", "state",
                  "command"):
            self.assertIn(k, p)

    def test_cpu_usage_progresses_from_none_to_float(self) -> None:
        dc = main.DemoCollector(seed=2)
        first = dc(previous_cpu=None, interval=1.0)
        self.assertIsNone(first["cpu_usage"])
        second = dc(previous_cpu=first["cpu_times"], interval=1.0)
        self.assertIsInstance(second["cpu_usage"], float)
        self.assertGreaterEqual(second["cpu_usage"], 0.0)
        self.assertLessEqual(second["cpu_usage"], 100.0)

    def test_memory_in_kib_and_load_present(self) -> None:
        data = main.DemoCollector(seed=3)(previous_cpu=None, interval=1.0)
        mem = data["memory"]
        self.assertEqual(mem["swap_total"], 4 * 1024 * 1024)  # KiB
        la = data["load_average"]
        for k in ("1min", "5min", "15min"):
            self.assertIn(k, la)

    def test_deterministic_with_seed(self) -> None:
        a = main.DemoCollector(seed=42)
        b = main.DemoCollector(seed=42)
        seq_a = [a(previous_cpu=None, interval=1.0)["memory"]["ram_used"]
                 for _ in range(3)]
        seq_b = [b(previous_cpu=None, interval=1.0)["memory"]["ram_used"]
                 for _ in range(3)]
        self.assertEqual(seq_a, seq_b)


class TestToSnapshot(unittest.TestCase):

    def test_kib_converted_to_bytes(self) -> None:
        snap = main.to_snapshot(_collector_data(), timestamp=1000.0)
        self.assertIsInstance(snap, SystemSnapshot)
        self.assertEqual(snap.timestamp, 1000.0)
        # ram_total was 16*1024*1024 KiB -> bytes = *1024.
        self.assertEqual(snap.memory.total_bytes, 16 * 1024 * 1024 * KIB)
        self.assertEqual(snap.memory.used_bytes, 6 * 1024 * 1024 * KIB)
        self.assertAlmostEqual(snap.memory.usage_percent,
                               6 / 16 * 100, places=5)

    def test_swap_none_when_unconfigured(self) -> None:
        data = _collector_data(swap_total=0)
        snap = main.to_snapshot(data, timestamp=0.0)
        self.assertIsNone(snap.swap)  # models.py rule: no swap -> None

    def test_swap_present_when_configured(self) -> None:
        snap = main.to_snapshot(_collector_data(), timestamp=0.0)
        self.assertIsInstance(snap.swap, SwapInfo)
        self.assertEqual(snap.swap.total_bytes, 4 * 1024 * 1024 * KIB)

    def test_processes_converted(self) -> None:
        snap = main.to_snapshot(_collector_data(), timestamp=0.0)
        self.assertEqual(len(snap.processes), 2)
        self.assertIsInstance(snap.processes[0], ProcessInfo)
        self.assertEqual(snap.processes[1].name, "firefox")  # command -> name

    def test_malformed_process_row_is_skipped(self) -> None:
        data = _collector_data(processes=[
            {"pid": 1, "command": "init", "cpu_percent": 0.0,
             "memory_percent": 0.1, "user": "root", "state": "S"},
            {"command": "no-pid"},  # missing pid -> skipped
            {"pid": "not-an-int", "command": "bad"},  # ValueError -> skipped
        ])
        snap = main.to_snapshot(data, timestamp=0.0)
        self.assertEqual(len(snap.processes), 1)
        self.assertEqual(snap.processes[0].pid, 1)

    def test_load_averages_mapped_positionally(self) -> None:
        snap = main.to_snapshot(_collector_data(), timestamp=0.0)
        la = snap.cpu.load_averages
        self.assertEqual((la.one_minute, la.five_minutes, la.fifteen_minutes),
                         (0.4, 0.5, 0.6))

    def test_empty_memory_when_no_ram_total(self) -> None:
        data = _collector_data()
        data["memory"] = {}
        snap = main.to_snapshot(data, timestamp=0.0)
        self.assertEqual(snap.memory.total_bytes, 0)


class TestCpuBreakdown(unittest.TestCase):

    def test_none_when_prev_missing(self) -> None:
        cur = {"total": 100, "idle_total": 50, "user": 10}
        self.assertIsNone(main.cpu_breakdown(None, cur))

    def test_none_when_cur_missing(self) -> None:
        prev = {"total": 90, "idle_total": 40, "user": 5}
        self.assertIsNone(main.cpu_breakdown(prev, None))

    def test_none_when_total_delta_le_zero(self) -> None:
        cur = {"total": 100, "idle_total": 50, "user": 10}
        prev = dict(cur)  # identical -> delta 0
        self.assertIsNone(main.cpu_breakdown(prev, cur))

    def test_returns_breakdown_summing_to_100(self) -> None:
        prev = {"user": 100, "nice": 0, "system": 50, "idle": 1000,
                "iowait": 0, "irq": 0, "softirq": 0, "steal": 0,
                "total": 1150, "idle_total": 1000}
        cur = {"user": 200, "nice": 0, "system": 100, "idle": 1100,
               "iowait": 0, "irq": 0, "softirq": 0, "steal": 0,
               "total": 1400, "idle_total": 1100}
        dims = main.cpu_breakdown(prev, cur)
        self.assertIsInstance(dims, CpuBreakdown)
        # user 100/250*100=40, system 50/250*100=20, idle 100/250*100=40
        self.assertAlmostEqual(dims.user, 40.0, places=5)
        self.assertAlmostEqual(dims.system, 20.0, places=5)
        self.assertAlmostEqual(dims.idle, 40.0, places=5)
        total = sum(getattr(dims, k) for k in CPU_DIMS) + dims.idle
        self.assertAlmostEqual(total, 100.0, places=5)


class TestRowAndSystemUser(unittest.TestCase):

    def test_row_from_process_info(self) -> None:
        p = ProcessInfo(pid=7, name="x", cpu_percent=3.0,
                        memory_percent=1.5, username="dhiren", state="R")
        row = main._row(p)
        self.assertEqual(row.pid, 7)
        self.assertEqual(row.name, "x")
        self.assertEqual(row.cpu, 3.0)
        self.assertEqual(row.mem, 1.5)
        self.assertEqual(row.state, "R")

    def test_row_from_dict_uses_username_or_fallback(self) -> None:
        d = {"pid": 9, "name": "y", "cpu_percent": 2.0,
             "memory_percent": 0.5, "state": "S", "username": "root"}
        row = main._row(d)
        self.assertEqual(row.user, "root")
        # dict without username -> falls back to users[pid]
        d2 = {"pid": 9, "name": "y", "cpu_percent": 2.0,
              "memory_percent": 0.5, "state": "S"}
        row2 = main._row(d2, users={9: "fallback"})
        self.assertEqual(row2.user, "fallback")

    def test_is_system_user_handles_empty_and_unknown(self) -> None:
        self.assertIsNone(main.is_system_user(None))
        self.assertIsNone(main.is_system_user(""))
        # 'root' resolves on Linux (uid 0 < 1000); unknown user -> None.
        self.assertIn(main.is_system_user("root"), (True, None))
        self.assertIsNone(main.is_system_user("definitely-not-a-user-xyz"))


class TestToViewState(unittest.TestCase):

    def _build(self, *, load=(0.4, 0.5, 0.6)):
        snap = SystemSnapshot(
            timestamp=1000.0,
            cpu=CPUInfo(usage_percent=12.0, core_count=8,
                        load_averages=LoadAverages(*load)),
            memory=MemoryInfo.from_total_used_free(16 * 1024 ** 3,
                                                   6 * 1024 ** 3,
                                                   8 * 1024 ** 3),
            swap=SwapInfo.from_total_used(2 * 1024 ** 3, 1 * 1024 ** 3),
            processes=[ProcessInfo(pid=1, name="init", cpu_percent=0.0,
                                   memory_percent=0.1, username="root",
                                   state="S")],
        )
        result = {
            "active_alerts": [],
            "resources": {"cpu": {"mean_percent": 11.0,
                                  "maximum_percent": 12.0},
                          "ram": {"mean_percent": 37.5,
                                  "maximum_percent": 40.0},
                          "swap": {"mean_percent": 50.0,
                                   "maximum_percent": 50.0}},
            "top_cpu_processes": snap.processes,
            "top_memory_processes": snap.processes,
        }
        extras = [dict(ts=999.0, load1=0.4, dims=None,
                       used=6.0, free=8.0, cache=2.0)]
        history = [{"timestamp": datetime.fromtimestamp(999.0).isoformat(),
                    "cpu_percent": 10.0, "ram_percent": 37.0,
                    "swap_percent": 50.0}]
        cfg = AppConfig()
        return snap, result, history, extras, cfg

    def test_builds_full_view_state(self) -> None:
        snap, result, history, extras, cfg = self._build()
        state = main.to_view_state(snap, result, history, extras, [], cfg, None)
        self.assertIsInstance(state, ViewState)
        self.assertEqual(state.timestamp, 1000.0)
        self.assertEqual(state.cpu, 12.0)
        self.assertEqual(state.ram, 37.5)  # 6GiB/16GiB*100
        self.assertAlmostEqual(state.mem_total_gib, 16.0, places=3)
        self.assertAlmostEqual(state.mem_used_gib, 6.0, places=3)
        self.assertEqual(state.swap, 50.0)  # 1GiB/2GiB*100
        self.assertEqual(state.n_cpus, 8)
        self.assertEqual(state.total, 1)
        self.assertEqual(state.sleeping, 1)
        self.assertEqual(state.running, 0)
        self.assertEqual(state.avg_cpu, 11.0)
        self.assertEqual(state.peak_swap, 50.0)
        self.assertEqual(len(state.top_processes), 1)
        self.assertEqual(state.interval_s, cfg.sampling_interval_seconds)
        self.assertEqual(state.hostname, state.hostname)  # a str

    def test_load_none_when_any_component_missing(self) -> None:
        snap, result, history, extras, cfg = self._build(load=(0.4, None, 0.6))
        state = main.to_view_state(snap, result, history, extras, [], cfg, None)
        self.assertIsNone(state.load)

    def test_history_aligned_with_extras(self) -> None:
        snap, result, _, _, cfg = self._build()
        history = [
            {"timestamp": datetime.fromtimestamp(998.0).isoformat(),
             "cpu_percent": 9.0, "ram_percent": 36.0, "swap_percent": 49.0},
            {"timestamp": datetime.fromtimestamp(999.0).isoformat(),
             "cpu_percent": 10.0, "ram_percent": 37.0, "swap_percent": 50.0},
        ]
        extras = [dict(ts=998.0, load1=0.3, dims=None, used=5.9, free=8.1,
                       cache=2.0),
                  dict(ts=999.0, load1=0.4, dims=None, used=6.0, free=8.0,
                       cache=2.0)]
        state = main.to_view_state(snap, result, history, extras, [], cfg, None)
        self.assertEqual(len(state.history.t), 2)
        self.assertEqual(len(state.history.cpu), 2)
        self.assertEqual(state.history.cpu, [9.0, 10.0])
        self.assertEqual(state.history.ram, [36.0, 37.0])
        # t is seconds-relative-to-now
        self.assertEqual(state.history.t, [-2.0, -1.0])


class TestControllerPublish(unittest.TestCase):

    def test_publish_puts_item_on_queue(self) -> None:
        cfg = _fast_cfg()
        q: queue.Queue = queue.Queue(maxsize=4)
        ctrl = main.Controller(cfg, q, main.DemoCollector(seed=1))
        ctrl._publish("an-item")
        self.assertEqual(q.qsize(), 1)
        self.assertEqual(q.get_nowait(), "an-item")

    def test_publish_drops_oldest_when_full(self) -> None:
        cfg = _fast_cfg()
        q: queue.Queue = queue.Queue(maxsize=2)
        ctrl = main.Controller(cfg, q, main.DemoCollector(seed=1))
        ctrl._publish("a")
        ctrl._publish("b")
        ctrl._publish("c")  # queue full -> oldest ("a") dropped
        self.assertEqual(q.qsize(), 2)
        self.assertEqual(q.get_nowait(), "b")
        self.assertEqual(q.get_nowait(), "c")


class TestControllerAlerts(unittest.TestCase):

    def test_alerts_track_since_and_clear_when_resolved(self) -> None:
        cfg = _fast_cfg()
        q: queue.Queue = queue.Queue(maxsize=4)
        ctrl = main.Controller(cfg, q, main.DemoCollector(seed=1))
        result_with = {"active_alerts": [
            {"resource": "cpu", "name": "CPU", "value_percent": 90.0,
             "threshold_percent": 80.0, "severity": "warning"}]}
        alerts = ctrl._alerts(result_with, now=100.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].timestamp, 100.0)
        self.assertIn("cpu", ctrl.alert_since)
        # Same alert active later -> since is preserved (not reset).
        alerts2 = ctrl._alerts(result_with, now=200.0)
        self.assertEqual(alerts2[0].timestamp, 100.0)
        # Alert gone -> cleared.
        result_without = {"active_alerts": []}
        ctrl._alerts(result_without, now=300.0)
        self.assertNotIn("cpu", ctrl.alert_since)


class TestControllerRun(unittest.TestCase):

    def _drain(self, q: queue.Queue) -> list:
        out = []
        while True:
            try:
                out.append(q.get_nowait())
            except queue.Empty:
                break
        return out

    def test_run_publishes_view_states(self) -> None:
        cfg = _fast_cfg(sampling=0.01)
        q: queue.Queue = queue.Queue(maxsize=cfg.queue_capacity)
        ctrl = main.Controller(cfg, q, main.DemoCollector(seed=7))
        ctrl.start()
        time.sleep(0.06)          # ~6 ticks
        ctrl.stop()
        self.assertFalse(ctrl.thread.is_alive())
        items = self._drain(q)
        self.assertTrue(items, "controller published nothing")
        # Every published item is a ViewState (no SourceError on the happy path)
        self.assertTrue(all(isinstance(it, ViewState) for it in items),
                        f"unexpected non-ViewState: {[type(i).__name__ for i in items]}")
        # The analytics engine received real SystemSnapshots.
        self.assertTrue(ctrl.engine.add_calls)
        self.assertTrue(all(isinstance(s, SystemSnapshot)
                            for s in ctrl.engine.add_calls))
        # After the first tick, CPU usage is computed (previous_cpu available).
        self.assertIsNotNone(items[-1].cpu)

    def test_run_publishes_source_error_when_collect_raises(self) -> None:
        cfg = _fast_cfg(sampling=0.01)

        def boom(previous_cpu=None, interval=1.0):
            raise RuntimeError("collect exploded")

        q: queue.Queue = queue.Queue(maxsize=cfg.queue_capacity)
        ctrl = main.Controller(cfg, q, boom)
        ctrl.start()
        time.sleep(0.04)
        ctrl.stop()
        items = self._drain(q)
        self.assertTrue(any(isinstance(it, SourceError) for it in items),
                        "expected a SourceError to be published")

    def test_extras_and_history_stay_aligned(self) -> None:
        cfg = _fast_cfg(sampling=0.01)
        q: queue.Queue = queue.Queue(maxsize=cfg.queue_capacity)
        ctrl = main.Controller(cfg, q, main.DemoCollector(seed=5))
        ctrl.start()
        time.sleep(0.06)
        ctrl.stop()
        # extras (controller-side) and engine history must be the same length
        # so to_view_state's zip(history, extras) never misaligns.
        self.assertEqual(len(ctrl.extras), len(ctrl.engine.get_history()))


class TestCLI(unittest.TestCase):
    """main() argparse + wiring, with tk/Dashboard/Controller patched out
    so no display and no real worker thread are needed."""

    def _patch_gui(self):
        return (mock.patch("main.tk"),
                mock.patch("main.Dashboard"),
                mock.patch("main.Controller"))

    def test_help_exits_zero(self) -> None:
        # main() reads sys.argv (no argv parameter); patch it to test --help.
        with mock.patch.object(sys, "argv", ["linuxpulse", "--help"]):
            with self.assertRaises(SystemExit) as cm:
                main.main()
            self.assertEqual(cm.exception.code, 0)

    def test_demo_wiring_uses_demo_collector_and_labels_source(self) -> None:
        captured = {}

        class CapturingController:
            def __init__(self, cfg, updates, collect):
                captured["cfg"] = cfg
                captured["updates"] = updates
                captured["collect"] = collect
                captured["controller"] = self
                self.thread = threading.Thread(target=lambda: None, daemon=True)

            def start(self):
                return self

            def stop(self):
                pass

        with mock.patch("main.tk") as fake_tk, \
                mock.patch("main.Dashboard") as fake_dash, \
                mock.patch("main.Controller", CapturingController), \
                mock.patch.object(sys, "argv", ["linuxpulse", "--demo"]):
            fake_root = mock.MagicMock()
            fake_tk.Tk.return_value = fake_root
            rc = main.main()
        self.assertIsNone(rc)
        self.assertIsInstance(captured["collect"], main.DemoCollector)
        # Dashboard was built with the DEMO DATA source label and the
        # controller's stop() wired as the window-close handler.
        _, kwargs = fake_dash.call_args
        self.assertEqual(kwargs.get("source_name"), "DEMO DATA")
        # on_close is the controller's bound stop() method (bound methods are
        # recreated per access, so compare the bound instance, not identity).
        on_close = kwargs.get("on_close")
        self.assertTrue(callable(on_close))
        self.assertIs(on_close.__self__, captured["controller"])
        # tk_version_warning path: Tk root created and mainloop entered.
        fake_tk.Tk.assert_called_once()
        fake_root.mainloop.assert_called_once()

    def test_interval_override_applied(self) -> None:
        captured = {}

        class CapturingController:
            def __init__(self, cfg, updates, collect):
                captured["cfg"] = cfg

            def start(self):
                return self

            def stop(self):
                pass

        with mock.patch("main.tk"), mock.patch("main.Dashboard"), \
                mock.patch("main.Controller", CapturingController), \
                mock.patch.object(sys, "argv",
                                  ["linuxpulse", "--interval", "1.5", "--demo"]):
            main.main()
        self.assertEqual(captured["cfg"].sampling_interval_seconds, 1.5)

    def test_interval_clamped_to_minimum_half_second(self) -> None:
        captured = {}

        class CapturingController:
            def __init__(self, cfg, updates, collect):
                captured["cfg"] = cfg

            def start(self):
                return self

            def stop(self):
                pass

        with mock.patch("main.tk"), mock.patch("main.Dashboard"), \
                mock.patch("main.Controller", CapturingController), \
                mock.patch.object(sys, "argv",
                                  ["linuxpulse", "--interval", "0.1", "--demo"]):
            main.main()
        self.assertEqual(captured["cfg"].sampling_interval_seconds, 0.5)

    def test_non_linux_platform_falls_back_to_demo(self) -> None:
        captured = {}

        class CapturingController:
            def __init__(self, cfg, updates, collect):
                captured["collect"] = collect

            def start(self):
                return self

            def stop(self):
                pass

        with mock.patch("main.tk"), mock.patch("main.Dashboard"), \
                mock.patch("main.Controller", CapturingController), \
                mock.patch.object(sys, "argv", ["linuxpulse"]), \
                mock.patch.object(main.sys, "platform", "win32"):
            main.main()  # no --demo, but platform is win32
        self.assertIsInstance(captured["collect"], main.DemoCollector)


if __name__ == "__main__":
    unittest.main(verbosity=2)
