import sys

if sys.version_info < (3, 9):
    sys.exit("Python 3.9 or newer is required.")

try:
    import tkinter as tk
except ImportError:
    if sys.platform == "darwin":
        hint = "Install Python from python.org, or: brew install python python-tk"
    else:
        hint = ("Debian/Ubuntu: sudo apt install python3-tk   ·   Fedora: sudo dnf install python3-tkinter   ·   "
                "Arch: sudo pacman -S tk")
    sys.exit(f"Tkinter is not available for this Python ({sys.executable}).\n{hint}")

import importlib.util

if importlib.util.find_spec("matplotlib") is None:
    sys.exit(f"Matplotlib is missing. Run:  {sys.executable} -m pip install -r requirements.txt")

import argparse
import os
import queue
import random
import socket
import threading
import time
from collections import deque
from datetime import datetime

from analytics.engine import AnalyticsEngine
from collector.parser import calculate_cpu_usage
from config import AppConfig
from gui.dashboard import (CPU_DIMS, Alert, CpuBreakdown, Dashboard, History, ProcessRow, SourceError,
                           ViewState, tk_version_warning)
from models import CPUInfo, LoadAverages, MemoryInfo, ProcessInfo, SwapInfo, SystemSnapshot

GIB = 1024 ** 3
TOP_PROCESS_LIMIT = 8          # rows shown in the GUI's "top processes" lists


# ============================================================================
# Adapters
# ============================================================================
def to_snapshot(data, timestamp):
    """collector dict (KiB, plain keys) -> models.SystemSnapshot (bytes, typed)."""
    load = data.get("load_average") or {}
    cpu = CPUInfo(usage_percent=data.get("cpu_usage"),
                  core_count=int(data.get("cpu_cores") or 0),
                  load_averages=LoadAverages(load.get("1min"), load.get("5min"), load.get("15min")))
    mem = data.get("memory") or {}
    kib = 1024
    if mem.get("ram_total"):
        memory = MemoryInfo.from_total_used_free(mem["ram_total"] * kib, mem["ram_used"] * kib,
                                                 mem.get("ram_free", 0) * kib)
    else:
        memory = MemoryInfo()
    swap = (SwapInfo.from_total_used(mem["swap_total"] * kib, mem.get("swap_used", 0) * kib)
            if mem.get("swap_total") else None)            # no swap configured -> None (models.py rule)
    processes = []
    for p in data.get("processes") or []:
        try:
            processes.append(ProcessInfo(pid=int(p["pid"]), name=str(p.get("command") or ""),
                                         cpu_percent=p.get("cpu_percent"), memory_percent=p.get("memory_percent"),
                                         username=p.get("user"), state=p.get("state")))
        except (KeyError, TypeError, ValueError):
            continue                                        # skip a malformed row, keep the rest
    return SystemSnapshot(timestamp=timestamp, cpu=cpu, memory=memory, swap=swap, processes=processes)


def cpu_breakdown(prev, cur):
    """Per-dimension CPU % from two cumulative /proc/stat readings (collector 'cpu_times')."""
    if not prev or not cur:
        return None
    total = cur["total"] - prev["total"]
    if total <= 0:
        return None
    pct = {k: 100.0 * (cur[k] - prev[k]) / total for k in (*CPU_DIMS, "idle")}
    return CpuBreakdown(**pct)


_user_cache = {}


def _sys_uid(uid):
    return uid < 1000 or uid == 65534      # 65534 = nobody


def resolve_user(name):
    """top truncates long user names to 8 chars + '+' ('systemd+', 'rangero+').

    Returns (full_name, is_system): the full name if exactly one account matches the prefix,
    and is_system = True/False when every match agrees (Linux convention: UID < 1000), else None.
    """
    if not name:
        return name, None
    if name not in _user_cache:
        full, system = name, None
        try:
            import pwd
            if name.endswith("+"):
                prefix = name[:-1]
                hits = [e for e in pwd.getpwall() if e.pw_name.startswith(prefix)]
                if len(hits) == 1:
                    full = hits[0].pw_name
                if hits and len({_sys_uid(e.pw_uid) for e in hits}) == 1:
                    system = _sys_uid(hits[0].pw_uid)
            else:
                system = _sys_uid(pwd.getpwnam(name).pw_uid)
        except (ImportError, KeyError):
            pass
        _user_cache[name] = (full, system)
    return _user_cache[name]


def is_system_user(name):
    return resolve_user(name)[1]


def read_uptime():
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _epoch(iso):
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


def _row(p, users=None):
    """models.ProcessInfo or analytics process dict -> gui.ProcessRow."""
    get = p.get if isinstance(p, dict) else (lambda k, d=None: getattr(p, k, d))
    pid = get("pid")
    user = resolve_user(get("username") or (users or {}).get(pid))[0]
    return ProcessRow(pid=pid, name=get("name"), cpu=get("cpu_percent"), mem=get("memory_percent"),
                      state=get("state"), user=user, is_system=is_system_user(user))


def to_view_state(snap, result, history, extras, alerts, cfg, dims):
    """SystemSnapshot + analytics result + controller history -> gui.ViewState."""
    m, s, c = snap.memory, snap.swap, snap.cpu
    total = m.total_bytes or None
    la = c.load_averages
    load = (la.one_minute, la.five_minutes, la.fifteen_minutes)
    rows = [_row(p) for p in snap.processes]
    users = {r.pid: r.user for r in rows}
    states = [r.state for r in rows]
    res = result.get("resources", {})

    def stat(resource, key):
        return (res.get(resource) or {}).get(key)

    h = History()
    now = snap.timestamp
    for sample, extra in zip(history, extras):
        ts = _epoch(sample.get("timestamp")) or extra["ts"]
        h.t.append(ts - now)
        h.cpu.append(sample.get("cpu_percent"))
        h.ram.append(sample.get("ram_percent"))
        h.swap.append(sample.get("swap_percent"))
        h.load1.append(extra["load1"])
        h.mem_used.append(extra["used"])
        h.mem_buffcache.append(extra["cache"])
        h.mem_free.append(extra["free"])
        h.per_core.append(None)                     # collector reports aggregate CPU only
        for k in CPU_DIMS:
            h.cpu_dims.setdefault(k, []).append(extra["dims"].get(k) if extra["dims"] else None)

    return ViewState(
        timestamp=now, cpu=c.usage_percent, cpu_dims=dims, per_core=None, n_cpus=c.core_count or None,
        load=load if None not in load else None,
        ram=m.usage_percent,
        mem_total_gib=total / GIB if total else None,
        mem_used_gib=m.used_bytes / GIB if total else None,
        mem_free_gib=m.free_bytes / GIB if total else None,
        mem_buffcache_gib=max(0, m.total_bytes - m.used_bytes - m.free_bytes) / GIB if total else None,
        mem_available_gib=(m.total_bytes - m.used_bytes) / GIB if total else None,
        swap=s.usage_percent if s else None,
        swap_used_gib=s.used_bytes / GIB if s else None,
        swap_total_gib=s.total_bytes / GIB if s else 0.0,
        total=len(rows), running=states.count("R"),
        sleeping=sum(st in ("S", "I", "D") for st in states),
        stopped=sum(st in ("T", "t") for st in states), zombie=states.count("Z"),
        processes=rows, gpu_available=False, history=h,
        avg_cpu=stat("cpu", "mean_percent"), avg_ram=stat("ram", "mean_percent"),
        peak_cpu=stat("cpu", "maximum_percent"), peak_ram=stat("ram", "maximum_percent"),
        peak_swap=stat("swap", "maximum_percent"),
        top_processes=[_row(p, users) for p in result.get("top_cpu_processes", [])],
        top_memory_processes=[_row(p, users) for p in result.get("top_memory_processes", [])],
        alerts=alerts, uptime_s=read_uptime(), interval_s=cfg.sampling_interval_seconds,
        hostname=socket.gethostname())


# ============================================================================
# Interface compatibility checks (fail early, with an actionable message)
# ============================================================================
class IntegrationError(RuntimeError):
    """A module returned data, or exposes an interface, that does not match the agreed contract."""


COLLECTOR_KEYS = ("cpu_cores", "cpu_times", "load_average", "memory", "processes")
MEMORY_KEYS = ("ram_total", "ram_used", "ram_free")
ANALYTICS_KEYS = ("resources", "top_cpu_processes", "top_memory_processes", "active_alerts")


def validate_collector_data(data):
    """Collector output must be the agreed dict (KiB memory, cumulative cpu_times, process dicts)."""
    if not isinstance(data, dict):
        raise IntegrationError(f"collector returned {type(data).__name__}, expected a dict "
                               f"(see collector.top_collector.collect_system_data)")
    missing = [k for k in COLLECTOR_KEYS if k not in data]
    if missing:
        raise IntegrationError(f"collector data is missing key(s): {', '.join(missing)}")
    mem_missing = [k for k in MEMORY_KEYS if k not in (data["memory"] or {})]
    if mem_missing:
        raise IntegrationError(f"collector 'memory' is missing key(s): {', '.join(mem_missing)}")
    if not isinstance(data["processes"], (list, tuple)):
        raise IntegrationError(f"collector 'processes' is {type(data['processes']).__name__}, expected a list")
    times = data["cpu_times"]
    if not isinstance(times, dict) or "total" not in times:
        raise IntegrationError("collector 'cpu_times' must be a dict of cumulative counters including 'total'")
    return data


def validate_snapshot(snap):
    if not isinstance(snap, SystemSnapshot):
        raise IntegrationError(f"to_snapshot() produced {type(snap).__name__}, expected models.SystemSnapshot")
    return snap


def validate_analytics_result(result):
    """AnalyticsEngine.add_snapshot() must return the agreed analytics dict."""
    if not isinstance(result, dict):
        raise IntegrationError(f"analytics returned {type(result).__name__}, expected a dict "
                               f"(see analytics.engine.AnalyticsEngine.add_snapshot)")
    missing = [k for k in ANALYTICS_KEYS if k not in result]
    if missing:
        raise IntegrationError(f"analytics result is missing key(s): {', '.join(missing)}")
    return result


def validate_view_state(state):
    if not isinstance(state, ViewState):
        raise IntegrationError(f"to_view_state() produced {type(state).__name__}, expected gui.dashboard.ViewState")
    return state


def check_interfaces(collect=None):
    """Startup check that the teammate modules expose what main.py calls. Returns None or raises."""
    import inspect
    problems = []
    for name in ("add_snapshot", "get_history"):
        if not callable(getattr(AnalyticsEngine, name, None)):
            problems.append(f"analytics.engine.AnalyticsEngine has no method '{name}()'")
    try:
        params = inspect.signature(Dashboard).parameters
        if not any(p.kind is p.VAR_KEYWORD for p in params.values()):       # **kwargs accepts anything
            for p in ("root", "updates", "on_close", "source_name"):
                if p not in params:
                    problems.append(f"gui.dashboard.Dashboard() has no parameter '{p}'")
    except (TypeError, ValueError):
        pass                                                                  # signature not introspectable
    if collect is not None and not callable(collect):
        problems.append(f"collector {collect!r} is not callable")
    if problems:
        raise IntegrationError("incompatible module interface(s):\n  - " + "\n  - ".join(problems))


# ============================================================================
# Demo collector (same dict shape as collector.top_collector.collect_system_data)
# ============================================================================
class DemoCollector:
    """Synthetic system data for running on non-Linux machines or for demos.

    Returns exactly what Atharv's collect_system_data() returns (KiB memory, cumulative
    cpu_times, process dicts), so the adapter, analytics engine and GUI run unchanged.
    """
    NAMES = ["systemd", "kthreadd", "Xorg", "gnome-shell", "firefox", "code", "python3", "postgres",
             "dockerd", "pipewire", "sshd", "node", "java", "bash", "top", "NetworkManager"]

    def __init__(self, cores=None, seed=None):
        self.rng = random.Random(seed)
        self.cores = cores or os.cpu_count() or 4
        self.busy = 30.0
        self.times = {k: 0 for k in ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal")}
        self.total_kib, self.used = 16 * 1024 * 1024, 6.0 * 1024 * 1024
        self.load = self.cores * 0.3
        self.swap_total, self.swap_used = 4 * 1024 * 1024, 300 * 1024
        self.next_pid = 100 + 60 * 37
        self.procs = [dict(pid=100 + i * 37, command=self.rng.choice(self.NAMES), base=self.rng.choice([0, .1, .5, 2, 6]),
                           mem=round(self.rng.uniform(0, 5), 1), user=self.rng.choice(["root", "dhiren"]),
                           immortal=i < 3)             # first few behave like init/kernel threads
                      for i in range(60)]

    def _spawn(self):
        r = self.rng
        self.next_pid += r.randint(1, 40)
        return dict(pid=self.next_pid, command=r.choice(self.NAMES), base=r.choice([0, .1, .5, 2, 6]),
                    mem=round(r.uniform(0, 5), 1), user=r.choice(["root", "dhiren"]), immortal=False)

    def __call__(self, previous_cpu=None, interval=1.0):
        r = self.rng
        self.busy = max(2, min(99, self.busy + (30 - self.busy) * .05 + r.uniform(-8, 8) + (r.random() < .03) * 45))
        jiffies = 100 * self.cores * interval
        busy = jiffies * self.busy / 100
        share = {"user": .64, "system": .25, "nice": .02, "iowait": .04, "irq": .01, "softirq": .04, "steal": 0}
        for k, v in share.items():
            self.times[k] += int(busy * v)
        self.times["idle"] += int(jiffies - busy)
        cur = dict(self.times, total=sum(self.times.values()),
                   idle_total=self.times["idle"] + self.times["iowait"])
        self.load = max(.05, self.load * .9 + self.cores * self.busy / 100 * .1)
        self.used = max(3e6, min(15e6, self.used + r.uniform(-6e4, 6e4)))
        free = self.total_kib - self.used - 3.2e6
        if r.random() < .10 and len(self.procs) > 20:                       # a process terminates
            self.procs.remove(r.choice([p for p in self.procs if not p["immortal"]]))
        if r.random() < .12 and len(self.procs) < 120:                       # a process is created
            self.procs.append(self._spawn())
        self.swap_used = max(0, min(self.swap_total, self.swap_used + r.uniform(-4e4, 4e4)))
        processes = []
        for p in self.procs:
            p["mem"] = round(max(0.0, min(30.0, p["mem"] + r.uniform(-.05, .05))), 2)   # memory drifts
            cpu = round(max(0, p["base"] * self.busy / 30 * r.uniform(.3, 1.7)), 1)
            processes.append(dict(pid=p["pid"], user=p["user"], cpu_percent=cpu, memory_percent=p["mem"],
                                  state="R" if cpu > 5 and r.random() < .6 else "S", command=p["command"]))
        swap_total, swap_used = self.swap_total, int(self.swap_used)
        return {
            "cpu_usage": calculate_cpu_usage(previous_cpu, cur) if previous_cpu else None,
            "cpu_cores": self.cores, "cpu_times": cur,
            "load_average": {"1min": round(self.load, 2), "5min": round(self.load * .93, 2),
                             "15min": round(self.load * .86, 2)},
            "memory": {"ram_total": int(self.total_kib), "ram_used": int(self.used), "ram_free": int(free),
                       "ram_available": int(self.total_kib - self.used),
                       "ram_usage_percent": self.used / self.total_kib * 100,
                       "swap_total": swap_total, "swap_used": swap_used, "swap_free": swap_total - swap_used,
                       "swap_usage_percent": swap_used / swap_total * 100},
            "processes": processes,
        }


# ============================================================================
# Application controller
# ============================================================================
class Controller:
    def __init__(self, cfg, updates, collect):
        self.cfg, self.updates, self.collect = cfg, updates, collect
        self.engine = AnalyticsEngine(history_size=cfg.history_limit,
                                      cpu_threshold=cfg.cpu_threshold_percent,
                                      ram_threshold=cfg.ram_threshold_percent,
                                      swap_threshold=cfg.swap_threshold_percent,
                                      top_process_limit=TOP_PROCESS_LIMIT)
        self.extras = deque(maxlen=cfg.history_limit)      # GUI-only series aligned with engine history
        self.alert_since = {}                               # resource -> time the alert became active
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name=cfg.collector_thread_name,
                                       daemon=cfg.collector_thread_daemon)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=self.cfg.shutdown_timeout_seconds)

    def _publish(self, item):
        try:
            self.updates.put_nowait(item)
        except queue.Full:                                  # GUI only needs the newest state
            try:
                self.updates.get_nowait()
            except queue.Empty:
                pass
            self.updates.put_nowait(item)

    def _alerts(self, result, now):
        active = result.get("active_alerts", [])
        keys = {a.get("resource") for a in active}
        for k in list(self.alert_since):
            if k not in keys:
                del self.alert_since[k]
        out = []
        for a in active:
            since = self.alert_since.setdefault(a.get("resource"), now)
            msg = f"{a.get('name', a.get('resource'))} at {a.get('value_percent')}% " \
                  f"(threshold {a.get('threshold_percent')}%)"
            out.append(Alert(level=a.get("severity", "warning"), message=msg, timestamp=since))
        return out

    def _run(self):
        interval = self.cfg.sampling_interval_seconds
        prev_times = None
        while not self.stop_event.is_set():
            started = time.time()
            try:
                data = self.collect(prev_times) if not isinstance(self.collect, DemoCollector) \
                    else self.collect(prev_times, interval)
                validate_collector_data(data)
                dims = cpu_breakdown(prev_times, data.get("cpu_times"))
                prev_times = data.get("cpu_times")
                snap = validate_snapshot(to_snapshot(data, started))
                result = validate_analytics_result(self.engine.add_snapshot(snap))
                m = snap.memory
                self.extras.append(dict(
                    ts=started, load1=snap.cpu.load_averages.one_minute,
                    dims={k: getattr(dims, k) for k in CPU_DIMS} if dims else None,
                    used=m.used_bytes / GIB if m.total_bytes else None,
                    free=m.free_bytes / GIB if m.total_bytes else None,
                    cache=max(0, m.total_bytes - m.used_bytes - m.free_bytes) / GIB if m.total_bytes else None))
                state = validate_view_state(to_view_state(snap, result, self.engine.get_history(),
                                                          list(self.extras), self._alerts(result, started),
                                                          self.cfg, dims))
                self._publish(state)
            except Exception as exc:                        # keep sampling; GUI shows SOURCE ERROR
                self._publish(SourceError(f"{type(exc).__name__}: {exc}"))
            self.stop_event.wait(max(0.0, interval - (time.time() - started)))


# ============================================================================
# Entry point
# ============================================================================
def main():
    ap = argparse.ArgumentParser(
        description="LinuxPulse — real-time Linux system monitor",
        epilog="Default: live data from the real collector. --mock/--demo: synthetic data, labelled "
               "'DEMO DATA' in the window; never mixed with live measurements.")
    ap.add_argument("--demo", "--mock", dest="demo", action="store_true",
                    help="synthetic data through the same pipeline (any OS); --mock as in README")
    ap.add_argument("--interval", type=float, help="sampling interval in seconds (default: config.py)")
    args = ap.parse_args()

    cfg = AppConfig.from_env()
    if args.interval:
        from dataclasses import replace
        cfg = replace(cfg, sampling_interval_seconds=max(0.5, args.interval))

    demo = args.demo
    if not demo and not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        print(f"Live collection supports Linux and macOS, not {sys.platform}. Starting in demo mode.",
              file=sys.stderr)
        demo = True
    if demo:
        collect = DemoCollector()
    else:
        from collector.top_collector import collect_system_data
        collect = collect_system_data

    try:
        check_interfaces(collect)
    except IntegrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    warning = tk_version_warning()
    if warning:
        print("WARNING:", warning, file=sys.stderr)

    print(f"LinuxPulse starting — source: {'MOCK (simulated data, not real measurements)' if demo else 'LIVE (real collector)'}"
          f" · interval {cfg.sampling_interval_seconds:g}s · history {cfg.history_limit} samples"
          f" · queue {cfg.queue_capacity} · close the window to exit")

    updates = queue.Queue(maxsize=cfg.queue_capacity)
    controller = Controller(cfg, updates, collect).start()
    root = tk.Tk(className="LinuxPulse")
    Dashboard(root, updates, on_close=controller.stop, source_name="DEMO DATA" if demo else "")
    root.mainloop()


if __name__ == "__main__":
    raise SystemExit(main())
