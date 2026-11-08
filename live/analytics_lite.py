"""TEMPORARY minimal analytics for the live sources (history, averages, peaks, alerts).

This stands in for the team's analytics module until it is wired in. It works
on plain per-sample dicts and fills the analytics fields of ``ViewState``.
"""
from collections import deque

from gui.view_state import CPU_DIMS, Alert, History

CPU_WARN, CPU_CRIT = 75.0, 90.0
RAM_WARN, RAM_CRIT = 85.0, 95.0
SWAP_WARN = 50.0
LOAD_WARN = 1.0          # 1-min load per CPU


class LiteAnalytics:
    def __init__(self, window=120):
        self.samples = deque(maxlen=window)
        self.alerts = deque(maxlen=20)
        self._active = {}    # alert key -> level currently raised

    def add(self, state):
        """Record ``state`` (a ViewState with current metrics) and fill its analytics fields."""
        dims = state.cpu_dims
        self.samples.append(dict(
            ts=state.timestamp, cpu=state.cpu, ram=state.ram, swap=state.swap,
            load1=state.load[0] if state.load else None,
            dims={k: getattr(dims, k) if dims else None for k in CPU_DIMS},
            per_core=[c.total for c in state.per_core] if state.per_core else None,
            used=state.mem_used_gib, cache=state.mem_buffcache_gib, free=state.mem_free_gib))
        S, now = list(self.samples), state.timestamp
        state.history = History(
            t=[x["ts"] - now for x in S], cpu=[x["cpu"] for x in S], ram=[x["ram"] for x in S],
            swap=[x["swap"] for x in S], load1=[x["load1"] for x in S],
            cpu_dims={k: [x["dims"][k] for x in S] for k in CPU_DIMS},
            per_core=[x["per_core"] for x in S], mem_used=[x["used"] for x in S],
            mem_buffcache=[x["cache"] for x in S], mem_free=[x["free"] for x in S])

        def stats(key):
            vals = [x[key] for x in S if x[key] is not None]
            return (sum(vals) / len(vals), max(vals)) if vals else (None, None)

        state.avg_cpu, state.peak_cpu = stats("cpu")
        state.avg_ram, state.peak_ram = stats("ram")
        _, state.peak_swap = stats("swap")
        state.top_processes = sorted((p for p in state.processes if p.cpu is not None),
                                     key=lambda p: p.cpu, reverse=True)[:8]
        self._check(state)
        state.alerts = list(self.alerts)
        return state

    def _raise(self, key, level, message, ts):
        """Log an alert only when a condition starts or escalates (no repeats every sample)."""
        prev = self._active.get(key)
        if level is None:
            self._active.pop(key, None)
        elif prev != level and not (prev == "critical" and level == "warning"):
            self._active[key] = level
            self.alerts.appendleft(Alert(level, message, ts))
        elif prev == "critical" and level == "warning":
            self._active[key] = level

    def _check(self, s):
        ts = s.timestamp

        def lvl(v, warn, crit=None):
            if v is None:
                return None
            if crit is not None and v >= crit:
                return "critical"
            return "warning" if v >= warn else None

        if s.cpu is not None:
            self._raise("cpu", lvl(s.cpu, CPU_WARN, CPU_CRIT), f"CPU utilization at {s.cpu:.0f}%", ts)
        if s.ram is not None:
            self._raise("ram", lvl(s.ram, RAM_WARN, RAM_CRIT), f"RAM utilization at {s.ram:.0f}%", ts)
        if s.swap is not None:
            self._raise("swap", lvl(s.swap, SWAP_WARN), f"swap utilization at {s.swap:.0f}%", ts)
        if s.load and s.cores:
            per = s.load[0] / s.cores
            self._raise("load", lvl(per, LOAD_WARN), f"load average {s.load[0]:.2f} on {s.cores} CPUs", ts)
        if s.zombie:
            self._raise("zombie", "warning", f"{s.zombie} zombie process(es)", ts)
        else:
            self._raise("zombie", None, "", ts)
