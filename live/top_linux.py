"""TEMPORARY live source for Linux: parses procps-ng `top` batch output into ViewState.

    top -b -1 -w 512 -d <interval>

Handles procps-ng 3.3.x and 4.x output, including 4.x's wide layout where several
%CpuN entries (and Mem + Swap) share one line. Replace with the team's collector
via an adapter once models.py is available.
"""
import os
import pwd
import queue
import re
import socket
import time

from gui.view_state import CPU_DIMS, CpuBreakdown, ProcessRow, ViewState

from .analytics_lite import LiteAnalytics
from .top_stream import TopStream

_UNIT_TO_GIB = {"KiB": 1 / 1024 ** 2, "MiB": 1 / 1024, "GiB": 1.0, "TiB": 1024.0, "PiB": 1024.0 ** 2}
_CPU_KEYS = {"us": "user", "sy": "system", "ni": "nice", "id": "idle", "wa": "iowait",
             "hi": "irq", "si": "softirq", "st": "steal"}

RE_LOAD = re.compile(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)")
RE_UP = re.compile(r"\bup\s+(.*?),\s+\d+\s+users?")
RE_TASKS = re.compile(r"Tasks:\s*(\d+)\s+total,\s*(\d+)\s+running,\s*(\d+)\s+sleeping,"
                      r"\s*(\d+)\s+stopped,\s*(\d+)\s+zombie")
RE_CPU_N = re.compile(r"%Cpu(\d+)\s*:\s*([^%]*)")
RE_CPU_ALL = re.compile(r"%Cpu\(s\)\s*:\s*([^%\n]*)")
RE_CPU_FIELD = re.compile(r"([\d.]+)\s*(us|sy|ni|id|wa|hi|si|st)\b")
RE_MEM = re.compile(r"(KiB|MiB|GiB|TiB|PiB)\s+Mem\s*:\s*([\d.]+)\s+total,\s*([\d.]+)\s+free,"
                    r"\s*([\d.]+)\s+used,\s*([\d.]+)\s+buff/cache")
RE_SWAP = re.compile(r"(KiB|MiB|GiB|TiB|PiB)\s+Swap\s*:\s*([\d.]+)\s+total,\s*([\d.]+)\s+free,"
                     r"\s*([\d.]+)\s+used\.\s*([\d.]+)\s+avail\s+Mem")


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_uptime(text):
    """'15 days,  3:12' | '3:12' | '45 min' | '1 day, 10 min' -> seconds."""
    if not text:
        return None
    secs, found = 0, False
    m = re.search(r"(\d+)\s+days?", text)
    if m:
        secs += int(m.group(1)) * 86400
        found = True
    m = re.search(r"(\d+):(\d+)", text)
    if m:
        secs += int(m.group(1)) * 3600 + int(m.group(2)) * 60
        found = True
    m = re.search(r"(\d+)\s+min", text)
    if m:
        secs += int(m.group(1)) * 60
        found = True
    return secs if found else None


def parse_mem_kib(s):
    """top RES: plain KiB, or with k/m/g/t/p suffix -> MiB."""
    if not s:
        return None
    s = s.strip().lower()
    mult = {"k": 1, "m": 1024, "g": 1024 ** 2, "t": 1024 ** 3, "p": 1024 ** 4}
    if s[-1] in mult:
        v = _f(s[:-1])
        return None if v is None else v * mult[s[-1]] / 1024
    v = _f(s)
    return None if v is None else v / 1024


def parse_time_plus(s):
    """TIME+ 'mm:ss.hh' (or 'mmmm:ss') -> seconds."""
    try:
        if ":" not in s:
            return float(s)
        m, sec = s.split(":", 1)
        return int(m) * 60 + float(sec)
    except (TypeError, ValueError):
        return None


def _cpu_breakdown(segment):
    vals = {_CPU_KEYS[k]: float(v) for v, k in RE_CPU_FIELD.findall(segment)}
    return CpuBreakdown(**vals) if "idle" in vals else None


_uid_cache = {}


def is_system_user(name, threshold=1000):
    """Linux convention: UIDs below 1000 are system accounts. None if unknown/truncated."""
    if not name or name.endswith("+"):
        return None
    if name not in _uid_cache:
        try:
            _uid_cache[name] = pwd.getpwnam(name).pw_uid < threshold
        except KeyError:
            _uid_cache[name] = None
    return _uid_cache[name]


def parse_frame(lines, now=None):
    """One `top -b` frame (list of lines) -> ViewState without analytics fields."""
    now = now or time.time()
    try:
        hdr_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("PID"))
    except StopIteration:
        hdr_idx = len(lines)
    header = "\n".join(lines[:hdr_idx])
    st = ViewState(timestamp=now, hostname=socket.gethostname(), gpu_available=False)

    m = RE_LOAD.search(header)
    if m:
        st.load = tuple(float(x) for x in m.groups())
    m = RE_UP.search(lines[0]) if lines else None
    st.uptime_s = parse_uptime(m.group(1)) if m else None
    m = RE_TASKS.search(header)
    if m:
        st.total, st.running, st.sleeping, st.stopped, st.zombie = (int(x) for x in m.groups())

    # CPU: per-core lines (from -1); fall back to the aggregate %Cpu(s) line
    per = {}
    for idx, seg in RE_CPU_N.findall(header):
        b = _cpu_breakdown(seg)
        if b:
            per[int(idx)] = b
    if per:
        st.per_core = [per[i] for i in sorted(per)]
        n = len(st.per_core)
        st.cpu_dims = CpuBreakdown(**{k: round(sum((getattr(c, k) or 0) for c in st.per_core) / n, 2)
                                      for k in CPU_DIMS + ("idle",)})
    else:
        m = RE_CPU_ALL.search(header)
        st.cpu_dims = _cpu_breakdown(m.group(1)) if m else None
    st.cpu = st.cpu_dims.total if st.cpu_dims else None
    st.n_cpus = len(st.per_core) if st.per_core else os.cpu_count()

    m = RE_MEM.search(header)
    if m:
        k = _UNIT_TO_GIB[m.group(1)]
        total, free, used, cache = (float(x) * k for x in m.groups()[1:])
        st.mem_total_gib, st.mem_free_gib, st.mem_used_gib, st.mem_buffcache_gib = total, free, used, cache
        st.ram = 100 * used / total if total else None
    m = RE_SWAP.search(header)
    if m:
        k = _UNIT_TO_GIB[m.group(1)]
        total, free, used, avail = (float(x) * k for x in m.groups()[1:])
        st.mem_available_gib = avail
        if total > 0:
            st.swap_total_gib, st.swap_used_gib = total, used
            st.swap = 100 * used / total
        else:
            st.swap_total_gib = 0.0     # no swap configured; swap % stays None

    # Process table
    if hdr_idx < len(lines):
        cols = lines[hdr_idx].split()
        idx = {c: i for i, c in enumerate(cols)}
        ncols = len(cols)
        rows = []
        for line in lines[hdr_idx + 1:]:
            if not line.strip():
                continue
            parts = line.split(None, ncols - 1)
            if len(parts) < ncols:
                continue

            def g(name):
                i = idx.get(name)
                return parts[i] if i is not None else None
            pid = g("PID")
            user = g("USER")
            rows.append(ProcessRow(
                pid=int(pid) if pid and pid.isdigit() else None, name=g("COMMAND"),
                cpu=_f(g("%CPU")), mem=_f(g("%MEM")), state=g("S"), user=user,
                res_mib=parse_mem_kib(g("RES")), time_s=parse_time_plus(g("TIME+")),
                is_system=is_system_user(user)))
        st.processes = rows
    return st


class TopLinuxSource:
    display_name = ""            # no badge: this is real data
    source_label = "top (procps)"

    def __init__(self, interval=1.0, window=120):
        self.interval, self.window = interval, window
        d = f"{interval:g}"
        self.stream = TopStream(
            [["top", "-b", "-1", "-w", "512", "-d", d],       # per-CPU lines (procps-ng 3.3.10+)
             ["top", "-b", "-w", "512", "-d", d],             # older top: aggregate CPU only
             ["top", "-b", "-d", d]],
            is_frame_start=lambda l: l.startswith("top - "))
        self.analytics = LiteAnalytics(window)

    def run(self, stop, out_q):
        first = True
        for frame in self.stream.frames(stop):
            if first:              # first frame's CPU% is averaged since boot — skip it
                first = False
                continue
            st = parse_frame(frame)
            st.interval_s = self.interval
            self.analytics.add(st)
            _put_latest(out_q, st)


def _put_latest(q, item):
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(item)
