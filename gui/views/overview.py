import tkinter as tk

from visualization.plots import StackedAreaPlot

from ..graph_panel import ChartPanel
from ..styles import CPU_COLORS, MEM_COLORS, P, level_color
from ..view_state import CPU_DIMS
from ..widgets import GaugeCard, IndexPanel, NumberCard, Panel, PerCoreBars, legend_chips
from .base import BaseView

CPU_LEGEND = [(k, k, CPU_COLORS[k]) for k in CPU_DIMS]
MEM_LEGEND = [("used", "used", MEM_COLORS["used"]), ("buffcache", "buff/cache", MEM_COLORS["buffcache"]),
              ("free", "free", MEM_COLORS["free"])]


def _gib(used, total):
    return "—" if used is None or total is None else f"{used:.1f} / {total:.1f} GiB"


def _frac(part, whole):
    return None if part is None or not whole else part / whole


class OverviewView(BaseView):
    title = "Overview"
    crumb = "System  ›  Overview"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, minsize=258)
        self.rowconfigure(0, weight=1)

        main = tk.Frame(self, bg=P["bg"])
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1, minsize=270)

        # ---- cards
        cards = tk.Frame(main, bg=P["bg"])
        cards.grid(row=0, column=0, sticky="ew")
        for i in range(5):
            cards.columnconfigure(i, weight=1, uniform="card")
        self.cpu = GaugeCard(cards, "Total CPU", icon="cpu")
        self.ram = GaugeCard(cards, "RAM used", icon="memory")
        self.swap = GaugeCard(cards, "Swap used", icon="swap")
        self.load = NumberCard(cards, "System load", unit="1m", icon="load")
        self.tasks = NumberCard(cards, "Tasks", unit="total", icon="tasks")
        for i, c in enumerate((self.cpu, self.ram, self.swap, self.load, self.tasks)):
            c.grid(row=0, column=i, sticky="nsew", padx=4, pady=4)

        # ---- per-core
        pc = Panel(main, title="Per-core utilization", context="cpu.cpuN", icon="cpu", pad=10)
        pc.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        legend_chips(pc.header_right, [("user", P["blue"]), ("system", P["red"]), ("other", P["amber"])])
        self.cores = PerCoreBars(pc.content)
        self.cores.pack(fill="x")

        # ---- charts
        charts = tk.Frame(main, bg=P["bg"])
        charts.grid(row=2, column=0, sticky="nsew")
        charts.columnconfigure(0, weight=5, uniform="ch")
        charts.columnconfigure(1, weight=3, uniform="ch")
        charts.rowconfigure(0, weight=1)
        self.cpu_plot = StackedAreaPlot(CPU_LEGEND, ylim=(0, 100))
        self.mem_plot = StackedAreaPlot(MEM_LEGEND, ylim=None, ylabel="GiB", yfmt="{:.0f}")
        self.cpu_chart = ChartPanel(charts, self.cpu_plot, "Total CPU utilization", "system.cpu", "cpu",
                                    legend=CPU_LEGEND, unit="%")
        self.mem_chart = ChartPanel(charts, self.mem_plot, "RAM utilization", "system.ram", "memory",
                                    legend=MEM_LEGEND, unit="GiB")
        self.cpu_chart.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.mem_chart.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        for ch in (self.cpu_chart, self.mem_chart):
            ch._last_update = lambda: self._state and self._update_charts(self._state)

        # ---- index
        self.index = IndexPanel(self, [
            ("CPU", "cpu", [(k, k) for k in CPU_DIMS]),
            ("Memory", "memory", [("m_used", "used"), ("m_cache", "buff/cache"), ("m_free", "free"),
                                  ("m_avail", "available")]),
            ("Swap", "swap", [("s_used", "used"), ("s_free", "free")]),
            ("Tasks", "tasks", [("t_run", "running"), ("t_sleep", "sleeping"), ("t_stop", "stopped"),
                                ("t_zomb", "zombie")]),
        ])
        self.index.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

    # ------------------------------------------------------------------ updates
    def update_state(self, s):
        self._state = s
        self.cpu.set(s.cpu, s.peak_cpu, f"peak {s.peak_cpu:.0f}% · {s.cores} CPUs" if s.cores and s.peak_cpu
                     is not None else "—")
        self.ram.set(s.ram, s.peak_ram, _gib(s.mem_used_gib, s.mem_total_gib))
        self.swap.set(s.swap, s.peak_swap, "no swap configured" if s.swap_total_gib == 0
                      else _gib(s.swap_used_gib, s.swap_total_gib))

        if s.load is None:
            self.load.set("—", "load average unavailable")
        else:
            pct = 100 * s.load[0] / s.cores if s.cores else None
            self.load.set(f"{s.load[0]:.2f}", f"5m {s.load[1]:.2f} · 15m {s.load[2]:.2f}",
                          color=level_color(pct) if pct is not None and pct >= 75 else None)
        self.tasks.set(str(s.total) if s.total is not None else "—",
                       f"{s.running if s.running is not None else '—'} running · "
                       f"{s.sleeping if s.sleeping is not None else '—'} sleeping")
        self.cores.set(s.per_core)
        self._update_index(s)
        self._update_charts(s)

    def _update_charts(self, s):
        h, now = s.history, s.timestamp
        times = [now + t for t in h.t]
        self.cpu_plot.update(times, h.cpu_dims)
        self.mem_plot.update(times, {"used": h.mem_used, "buffcache": h.mem_buffcache, "free": h.mem_free},
                             ymax=(s.mem_total_gib * 1.02) if s.mem_total_gib else None)
        d = s.cpu_dims
        self.cpu_chart.legend.set_values({k: getattr(d, k) if d else None for k in CPU_DIMS})
        self.mem_chart.legend.set_values({"used": s.mem_used_gib, "buffcache": s.mem_buffcache_gib,
                                          "free": s.mem_free_gib})
        self.cpu_chart.redraw()
        self.mem_chart.redraw()

    def _update_index(self, s):
        v = {}
        d = s.cpu_dims
        for k in CPU_DIMS:
            x = getattr(d, k) if d else None
            v[k] = ("—" if x is None else f"{x:.1f}%", None if x is None else x / 100)
        mt = s.mem_total_gib
        for key, x in (("m_used", s.mem_used_gib), ("m_cache", s.mem_buffcache_gib),
                       ("m_free", s.mem_free_gib), ("m_avail", s.mem_available_gib)):
            v[key] = ("—" if x is None else f"{x:.2f}G", _frac(x, mt))
        st = s.swap_total_gib
        sf = None if st is None or s.swap_used_gib is None else st - s.swap_used_gib
        v["s_used"] = ("—" if s.swap_used_gib is None else f"{s.swap_used_gib:.2f}G", _frac(s.swap_used_gib, st))
        v["s_free"] = ("—" if sf is None else f"{sf:.2f}G", _frac(sf, st))
        for key, x in (("t_run", s.running), ("t_sleep", s.sleeping), ("t_stop", s.stopped), ("t_zomb", s.zombie)):
            v[key] = ("—" if x is None else str(x), _frac(x, s.total))
        self.index.set_values(v)
