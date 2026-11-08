"""TEMPORARY live source for macOS (Intel / Apple Silicon): parses BSD `top -l` output.

    top -l 0 -s <interval> -n 400 -o cpu -stats pid,cpu,mem,user,state,time,command

macOS top has no per-CPU lines and no iowait/irq/steal, so those fields stay None and
the GUI shows them as unavailable. Swap comes from `sysctl vm.swapusage`, total RAM
from `sysctl hw.memsize`, uptime from `sysctl kern.boottime`.
"""
import os
import pwd
import re
import socket
import subprocess
import time

from gui.view_state import CpuBreakdown, ProcessRow, ViewState

from .analytics_lite import LiteAnalytics
from .top_linux import _put_latest
from .top_stream import TopStream

RE_PROCS = re.compile(r"Processes:\s*(\d+)\s+total,\s*(\d+)\s+running,(?:\s*(\d+)\s+stuck,)?\s*(\d+)\s+sleeping")
RE_LOAD = re.compile(r"Load Avg:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)")
RE_CPU = re.compile(r"CPU usage:\s*([\d.]+)%\s*user,\s*([\d.]+)%\s*sys,\s*([\d.]+)%\s*idle")
RE_PHYS = re.compile(r"PhysMem:\s*([\d.]+[BKMGT])\s+used.*?,\s*([\d.]+[BKMGT])\s+unused")
RE_SWAP = re.compile(r"total\s*=\s*([\d.]+)([KMGT])\s+used\s*=\s*([\d.]+)([KMGT])")
_STATE = {"running": "R", "sleeping": "S", "stuck": "D", "zombie": "Z", "stopped": "T", "halted": "T",
          "idle": "I"}
_MULT = {"B": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def size_bytes(s):
    """'1234K', '56M+', '2.1G-' -> bytes."""
    if not s:
        return None
    s = s.rstrip("+-")
    try:
        return float(s[:-1]) * _MULT[s[-1].upper()] if s[-1].upper() in _MULT else float(s)
    except (ValueError, KeyError):
        return None


def parse_time(s):
    """'1:23.45' (m:s) or '12:34:56' (h:m:s) -> seconds."""
    try:
        parts = [float(p) for p in s.split(":")]
    except (AttributeError, ValueError):
        return None
    secs = 0.0
    for p in parts:
        secs = secs * 60 + p
    return secs


def _sysctl(name):
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


_uid_cache = {}


def is_system_user(name):
    """macOS: regular accounts start at UID 501; daemons are '_name' or < 500."""
    if not name:
        return None
    if name.startswith("_") or name == "root":
        return True
    if name not in _uid_cache:
        try:
            _uid_cache[name] = pwd.getpwnam(name).pw_uid < 500
        except KeyError:
            _uid_cache[name] = None
    return _uid_cache[name]


def parse_frame(lines, mem_total_bytes=None, swap_line="", boot_epoch=None, now=None):
    now = now or time.time()
    try:
        hdr_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("PID"))
    except StopIteration:
        hdr_idx = len(lines)
    header = "\n".join(lines[:hdr_idx])
    st = ViewState(timestamp=now, hostname=socket.gethostname(), gpu_available=False, n_cpus=os.cpu_count())

    m = RE_PROCS.search(header)
    if m:
        st.total, st.running = int(m.group(1)), int(m.group(2))
        st.sleeping = int(m.group(4)) + (int(m.group(3)) if m.group(3) else 0)
    m = RE_LOAD.search(header)
    if m:
        st.load = tuple(float(x) for x in m.groups())
    m = RE_CPU.search(header)
    if m:
        u, s, i = (float(x) for x in m.groups())
        st.cpu_dims = CpuBreakdown(user=u, system=s, idle=i)   # nice/iowait/irq/softirq/steal: n/a on macOS
        st.cpu = st.cpu_dims.total

    m = RE_PHYS.search(header)
    if m:
        used, unused = size_bytes(m.group(1)), size_bytes(m.group(2))
        total = mem_total_bytes or (used + unused if used is not None and unused is not None else None)
        if used is not None and total:
            g = 1024 ** 3
            st.mem_total_gib, st.mem_used_gib = total / g, used / g
            st.mem_free_gib = unused / g if unused is not None else None
            st.mem_available_gib = max(0.0, (total - used) / g)
            st.ram = 100 * used / total
    m = RE_SWAP.search(swap_line or "")
    if m:
        total = float(m.group(1)) * _MULT[m.group(2)]
        used = float(m.group(3)) * _MULT[m.group(4)]
        if total > 0:
            st.swap_total_gib, st.swap_used_gib = total / 1024 ** 3, used / 1024 ** 3
            st.swap = 100 * used / total
        else:
            st.swap_total_gib = 0.0
    if boot_epoch:
        st.uptime_s = now - boot_epoch

    if hdr_idx < len(lines):
        cols = lines[hdr_idx].split()
        idx = {c: i for i, c in enumerate(cols)}
        n = len(cols)
        rows = []
        for line in lines[hdr_idx + 1:]:
            parts = line.split(None, n - 1)
            if len(parts) < n:
                continue

            def g(name):
                i = idx.get(name)
                return parts[i] if i is not None else None
            mem_b = size_bytes(g("MEM"))
            pid = g("PID")
            user = g("USER")
            try:
                cpu = float(g("%CPU"))
            except (TypeError, ValueError):
                cpu = None
            rows.append(ProcessRow(
                pid=int(pid) if pid and pid.isdigit() else None, name=g("COMMAND"), cpu=cpu,
                mem=(100 * mem_b / mem_total_bytes) if mem_b is not None and mem_total_bytes else None,
                state=_STATE.get((g("STATE") or "").lower()), user=user,
                res_mib=mem_b / 1024 ** 2 if mem_b is not None else None,
                time_s=parse_time(g("TIME")), is_system=is_system_user(user)))
        st.processes = rows
        st.stopped = sum(r.state == "T" for r in rows)
        st.zombie = sum(r.state == "Z" for r in rows)
    return st


class TopMacSource:
    display_name = ""
    source_label = "top (macOS)"

    def __init__(self, interval=1.0, window=120):
        self.interval = interval
        s = str(max(1, round(interval)))          # macOS top -s takes whole seconds
        stats = "pid,cpu,mem,user,state,time,command"
        self.stream = TopStream(
            [["top", "-l", "0", "-s", s, "-n", "400", "-o", "cpu", "-stats", stats]],
            is_frame_start=lambda l: l.startswith("Processes:"))
        self.analytics = LiteAnalytics(window)
        self.mem_total = _f_int(_sysctl("hw.memsize"))
        m = re.search(r"sec\s*=\s*(\d+)", _sysctl("kern.boottime"))
        self.boot = int(m.group(1)) if m else None

    def run(self, stop, out_q):
        first = True
        for frame in self.stream.frames(stop):
            if first:              # first sample has no CPU deltas
                first = False
                continue
            st = parse_frame(frame, self.mem_total, _sysctl("vm.swapusage"), self.boot)
            st.interval_s = self.interval
            self.analytics.add(st)
            _put_latest(out_q, st)


def _f_int(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None
