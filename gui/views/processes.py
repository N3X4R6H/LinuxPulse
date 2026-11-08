import time
import tkinter as tk

from .. import config
from ..platform_support import bind_shortcut
from ..process_table import ProcessTable
from ..styles import P, FONTS
from ..widgets import AlertList, BarList, Panel, SearchEntry, StatusDot, TabControl
from .base import BaseView

FILTERS = ("All", "High CPU", "High GPU", "System")


class _Stat(tk.Frame):
    def __init__(self, master, label, color):
        super().__init__(master, bg=P["panel"])
        top = tk.Frame(self, bg=P["panel"])
        top.pack(anchor="w")
        tk.Frame(top, bg=color, width=8, height=8).pack(side="left", padx=(0, 6))
        tk.Label(top, text=label, font=FONTS["tiny"], fg=P["text_dim"], bg=P["panel"]).pack(side="left")
        self.value = tk.Label(self, text="—", font=FONTS["number_md"], fg=P["text"], bg=P["panel"])
        self.value.pack(anchor="w")

    def set(self, v):
        self.value.config(text="—" if v is None else str(v), fg=P["text"] if v is not None else P["text_faint"])


class ProcessesView(BaseView):
    title = "Processes"
    crumb = "System  ›  Processes"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.columnconfigure(0, weight=5, uniform="t")
        self.columnconfigure(1, weight=4, uniform="t")
        self.columnconfigure(2, weight=4, uniform="t")
        self.rowconfigure(1, weight=1)
        self._filter = "All"

        st = Panel(self, title="Tasks", context="top", icon="tasks")
        st.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.status = StatusDot(st.header_right)
        self.status.pack(side="right")
        stats = tk.Frame(st.content, bg=P["panel"])
        stats.pack(fill="x", pady=(4, 0))
        self.stats = {}
        for i, (key, label, col) in enumerate((("total", "total", P["text_dim"]), ("running", "running", P["accent"]),
                                               ("sleeping", "sleeping", P["blue"]), ("stopped", "stopped", P["amber"]),
                                               ("zombie", "zombie", P["violet"]))):
            stats.columnconfigure(i, weight=1)
            w = _Stat(stats, label, col)
            w.grid(row=0, column=i, sticky="w")
            self.stats[key] = w
        self.meta = tk.Label(st.content, text="", font=FONTS["mono_sm"], fg=P["text_faint"], bg=P["panel"], anchor="w")
        self.meta.pack(fill="x", pady=(12, 0))

        tp = Panel(self, title="Top 5 processes", context="by %CPU", icon="cpu")
        tp.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self.top5 = BarList(tp.content, rows=5, empty_text="No processes available")
        self.top5.pack(fill="both", expand=True)

        al = Panel(self, title="Recent alerts", icon="bell")
        al.grid(row=0, column=2, sticky="nsew", padx=4, pady=4)
        self.alerts = AlertList(al.content, limit=4)
        self.alerts.pack(fill="both", expand=True)

        tb = Panel(self, title="Processes", context="top -b", icon="processes", pad=10)
        tb.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)
        self.table = ProcessTable(tb.content)
        bar = tk.Frame(tb.content, bg=P["panel"])
        bar.pack(fill="x", pady=(0, 8))
        self.search = SearchEntry(bar, self.table.set_query, placeholder="Search PID, user or command")
        self.search.pack(side="left")
        self.tabs = TabControl(bar, FILTERS, self._on_filter)
        self.tabs.pack(side="left", padx=(16, 0))
        tk.Label(bar, textvariable=self.table.count_var, font=FONTS["mono_sm"], fg=P["text_faint"],
                 bg=P["panel"]).pack(side="right")
        tk.Label(bar, text="processes", font=FONTS["tiny"], fg=P["text_faint"], bg=P["panel"]
                 ).pack(side="right", padx=(0, 6))
        self.table.pack(fill="both", expand=True)
        bind_shortcut(self, "f", lambda e: self.search.entry.focus_set() if self.winfo_ismapped() else None)

    def _on_filter(self, name):
        self._filter = name
        self._apply_filter()

    def _apply_filter(self):
        s, name, t = self._state, self._filter, self.table
        if name == "All":
            t.set_filter(None, "No processes available.")
        elif name == "High CPU":
            t.set_filter(lambda r: r.cpu is not None and r.cpu >= config.HIGH_CPU_MIN,
                         f"No processes above {config.HIGH_CPU_MIN:g}% CPU.", sort=("cpu", True))
        elif name == "High GPU":
            if s is not None and s.gpu_available:
                t.set_filter(lambda r: r.gpu is not None and r.gpu > 0, "No GPU-consuming processes.")
            else:
                t.set_filter(lambda r: False, "GPU telemetry unavailable — top has no per-process GPU metric.\n"
                                              "Connect a separate GPU collector to enable this filter.")
        elif name == "System":
            if s is not None and any(r.is_system is not None for r in s.processes):
                t.set_filter(lambda r: r.is_system is True, "No system processes.")
            else:
                t.set_filter(lambda r: False, "System classification not provided by the collector.")

    def update_state(self, s):
        first = self._state is None
        self._state = s
        if first:
            self._apply_filter()
        self.status.set(getattr(self.app, "status_text", "LIVE"), getattr(self.app, "status_color", P["accent"]))
        for key, w in self.stats.items():
            w.set(getattr(s, key))
        bits = []
        if s.interval_s:
            bits.append(f"refresh {s.interval_s:g}s")
        bits.append("updated " + time.strftime("%H:%M:%S", time.localtime(s.timestamp)))
        if s.load:
            bits.append("load avg " + ", ".join(f"{x:.2f}" for x in s.load))
        self.meta.config(text="   ·   ".join(bits))
        self.top5.set_items([(r.name, r.cpu) for r in s.top_processes[:5]])
        self.alerts.set_alerts(s.alerts)
        self.table.set_rows(s.processes)
