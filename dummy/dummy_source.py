"""TEMPORARY synthetic data source — for GUI development only.

Produces ``ViewState`` objects shaped like what ``top`` reports (header lines,
per-CPU lines, process table) so every widget can be exercised. It is NOT a
collector and NOT the analytics module; the top bar shows a "DEMO DATA" badge
while it is in use. Delete this package once the real backend is wired in.

Env flags for testing edge cases:
    DASH_DUMMY_EMPTY=1   -> empty process list
    DASH_DUMMY_NOSWAP=1  -> swap unavailable (None)
    DASH_DUMMY_CORES=N   -> pretend the machine has N logical CPUs
"""
import os
import queue
import random
import socket
import time
from collections import deque

from gui.view_state import CPU_DIMS, Alert, CpuBreakdown, History, ProcessRow, ViewState

_PROCS = [  # (command, user, base %cpu, res MiB, system?)
    ("systemd", "root", .1, 12, True), ("kthreadd", "root", 0, 0, True), ("rcu_sched", "root", .2, 0, True),
    ("systemd-journald", "root", .3, 48, True), ("systemd-udevd", "root", .1, 9, True),
    ("systemd-logind", "root", 0, 7, True), ("dbus-daemon", "messagebus", .1, 5, True),
    ("NetworkManager", "root", .2, 19, True), ("sshd", "root", 0, 8, True), ("cron", "root", 0, 3, True),
    ("rsyslogd", "syslog", .1, 6, True), ("polkitd", "polkitd", 0, 11, True), ("containerd", "root", .8, 52, True),
    ("dockerd", "root", .6, 88, True), ("Xorg", "root", 2.5, 140, True), ("gnome-shell", "dhiren", 6, 410, False),
    ("pipewire", "dhiren", 1.2, 22, False), ("wireplumber", "dhiren", .4, 18, False),
    ("firefox", "dhiren", 9, 860, False), ("Isolated Web Co", "dhiren", 4, 310, False),
    ("code", "dhiren", 5, 620, False), ("python3", "dhiren", 12, 145, False), ("postgres", "postgres", 1.5, 96, False),
    ("redis-server", "redis", .7, 14, False), ("nginx", "www-data", .3, 11, False), ("bash", "dhiren", 0, 5, False),
    ("tmux: server", "dhiren", .1, 6, False), ("top", "dhiren", .7, 4, False), ("node", "dhiren", 3, 210, False),
    ("java", "dhiren", 4, 700, False), ("gcc", "dhiren", 0, 40, False), ("make", "dhiren", 0, 6, False),
]


class DummySource:
    display_name = "DEMO DATA"

    def __init__(self, interval=1.0, window=120, seed=None):
        self.interval, self.window = interval, window
        self.rng = random.Random(seed)
        self.n_cores = int(os.environ.get("DASH_DUMMY_CORES", 0)) or os.cpu_count() or 8
        self.mem_total, self.swap_total = 15.52, 4.0
        self.core_load = [self.rng.uniform(10, 40) for _ in range(self.n_cores)]
        self.mem_used, self.buffcache, self.swap_used = 6.1, 3.4, 0.31
        self.load = self.n_cores * 0.3
        self.uptime0 = time.time() - 15 * 3600 - 31 * 60
        self.hist = deque(maxlen=window)
        self.alerts = deque(maxlen=12)
        self.empty = os.environ.get("DASH_DUMMY_EMPTY") == "1"
        self.noswap = os.environ.get("DASH_DUMMY_NOSWAP") == "1"
        self.procs = []
        pid = 1
        for name, user, base, res, sysp in _PROCS * 3:
            self.procs.append(dict(pid=pid, name=name, user=user, base=base, res=res * self.rng.uniform(.8, 1.2),
                                   sys=sysp, time=self.rng.uniform(0, 4000) if base else self.rng.uniform(0, 5)))
            pid += self.rng.randint(1, 900)
        self.procs[4]["res"] = None   # demonstrate a missing field

    def _walk(self, v, lo, hi, step, pull=None, k=0.05):
        if pull is not None:
            v += (pull - v) * k
        return max(lo, min(hi, v + self.rng.uniform(-step, step)))

    def _cores(self):
        r = self.rng
        spike = r.random() < 0.03
        cores = []
        for i in range(self.n_cores):
            self.core_load[i] = self._walk(self.core_load[i], 1, 99, 10, pull=28)
            if spike and r.random() < 0.6:
                self.core_load[i] = min(99, self.core_load[i] + r.uniform(30, 60))
            busy = self.core_load[i]
            sh = [r.uniform(.55, .7), r.uniform(.18, .28), r.uniform(0, .03), r.uniform(.01, .08),
                  r.uniform(0, .02), r.uniform(.01, .05), 0.0]
            tot = sum(sh)
            vals = [busy * x / tot for x in sh]
            cores.append(CpuBreakdown(*[round(v, 1) for v in vals], idle=round(100 - busy, 1)))
        return cores

    def _step(self, now=None):
        now = now or time.time()
        r = self.rng
        cores = self._cores()
        n = len(cores)
        dims = CpuBreakdown(**{k: round(sum(getattr(c, k) for c in cores) / n, 1) for k in CPU_DIMS},
                            idle=round(sum(c.idle for c in cores) / n, 1))
        cpu = dims.total
        self.load = max(0.02, self.load * .92 + n * cpu / 100 * .08 + r.uniform(-.05, .05))
        self.mem_used = self._walk(self.mem_used, 3.5, 13.5, .08, pull=6.3, k=.02)
        self.buffcache = self._walk(self.buffcache, 1.5, 5, .03)
        free = self.mem_total - self.mem_used - self.buffcache
        avail = free + self.buffcache * .85
        self.swap_used = self._walk(self.swap_used, 0, 1.6, .01)
        swap_pct = None if self.noswap else 100 * self.swap_used / self.swap_total
        ram = 100 * self.mem_used / self.mem_total

        rows = []
        if not self.empty:
            scale = cpu / 30
            for p in self.procs:
                c = max(0.0, p["base"] * scale * r.uniform(.3, 1.7) + (r.random() < .01) * r.uniform(10, 70))
                p["time"] += c / 100 * self.interval
                st = "R" if c > 8 and r.random() < .6 else r.choice("SSSSSSSSSSIID")
                rows.append(ProcessRow(pid=p["pid"], name=p["name"], cpu=round(c, 1),
                                       mem=None if p["res"] is None else round(100 * p["res"] / 1024 / self.mem_total, 1),
                                       state=st, user=p["user"], res_mib=p["res"], time_s=p["time"],
                                       is_system=p["sys"]))
            rows.append(ProcessRow(pid=31337, name="defunct-worker", cpu=0.0, mem=0.0, state="Z", user="dhiren",
                                   res_mib=0.0, time_s=0.0, is_system=False))

        self.hist.append(dict(ts=now, cpu=cpu, ram=ram, swap=swap_pct, load1=self.load,
                              dims={k: getattr(dims, k) for k in CPU_DIMS}, per_core=[c.total for c in cores],
                              used=self.mem_used, cache=self.buffcache, free=free))
        if cpu > 85:
            self.alerts.appendleft(Alert("critical", f"system.cpu utilization at {cpu:.0f}%", now))
        elif self.load / n > .8 and r.random() < .3:
            self.alerts.appendleft(Alert("warning", f"load average {self.load:.2f} on {n} CPUs", now))
        if not self.alerts:
            self.alerts.append(Alert("warning", "demo: 10min disk backlog above threshold", now - 95))

        H = list(self.hist)
        h = History(t=[x["ts"] - now for x in H], cpu=[x["cpu"] for x in H], ram=[x["ram"] for x in H],
                    swap=[x["swap"] for x in H], load1=[x["load1"] for x in H],
                    cpu_dims={k: [x["dims"][k] for x in H] for k in CPU_DIMS},
                    per_core=[x["per_core"] for x in H], mem_used=[x["used"] for x in H],
                    mem_buffcache=[x["cache"] for x in H], mem_free=[x["free"] for x in H])
        cpus = [v for v in h.cpu if v is not None]
        rams = [v for v in h.ram if v is not None]
        swaps = [v for v in h.swap if v is not None]
        top = sorted((p for p in rows if p.cpu is not None), key=lambda p: p.cpu, reverse=True)[:8]
        return ViewState(
            timestamp=now, cpu=cpu, cpu_dims=dims, per_core=cores,
            load=(self.load, self.load * .93, self.load * .85),
            ram=ram, mem_total_gib=self.mem_total, mem_used_gib=self.mem_used, mem_free_gib=free,
            mem_buffcache_gib=self.buffcache, mem_available_gib=avail,
            swap=swap_pct, swap_used_gib=None if self.noswap else self.swap_used,
            swap_total_gib=None if self.noswap else self.swap_total,
            total=len(rows), running=sum(p.state == "R" for p in rows),
            sleeping=sum(p.state in "SID" for p in rows), stopped=sum(p.state == "T" for p in rows),
            zombie=sum(p.state == "Z" for p in rows), processes=rows, gpu_available=False,
            history=h, avg_cpu=sum(cpus) / len(cpus) if cpus else None,
            avg_ram=sum(rams) / len(rams) if rams else None,
            peak_cpu=max(cpus, default=None), peak_ram=max(rams, default=None), peak_swap=max(swaps, default=None),
            top_processes=top, alerts=list(self.alerts), uptime_s=now - self.uptime0,
            interval_s=self.interval, hostname=socket.gethostname(),
        )

    def run(self, stop, out_q):
        start = time.time() - self.window * self.interval
        for i in range(self.window):            # backfilled history so charts start full
            self._step(now=start + i * self.interval)
        while not stop.is_set():
            state = self._step()
            try:
                out_q.put_nowait(state)
            except queue.Full:
                try:
                    out_q.get_nowait()
                except queue.Empty:
                    pass
                out_q.put_nowait(state)
            stop.wait(self.interval)
