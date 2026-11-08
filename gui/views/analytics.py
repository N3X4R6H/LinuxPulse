import tkinter as tk

from visualization.plots import AnalyticsGrid

from ..graph_panel import ChartPanel
from ..styles import P, SERIES_COLORS, level_color
from ..widgets import AlertList, BarList, NumberCard, Panel
from .base import BaseView


class AnalyticsView(BaseView):
    title = "Analytics"
    crumb = "System  ›  Analytics"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, minsize=330)
        self.rowconfigure(1, weight=1)

        strip = tk.Frame(self, bg=P["bg"])
        strip.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.tiles = {}
        for i, (key, label, icon) in enumerate((("avg_cpu", "Average CPU", "cpu"), ("avg_ram", "Average RAM", "memory"),
                                                ("peak_cpu", "Peak CPU", "cpu"), ("peak_ram", "Peak RAM", "memory"),
                                                ("peak_swap", "Peak swap", "swap"))):
            strip.columnconfigure(i, weight=1, uniform="t")
            t = NumberCard(strip, label, unit="%", icon=icon, big=False, pad=8)
            t.grid(row=0, column=i, sticky="nsew", padx=4, pady=4)
            self.tiles[key] = t

        self.grid_plot = AnalyticsGrid(SERIES_COLORS)
        self.chart = ChartPanel(self, self.grid_plot, "Utilization history", "last 2 min · dashed = average",
                                "analytics", min_h=320)
        self.chart.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        side = tk.Frame(self, bg=P["bg"])
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        tp = Panel(side, title="Top resource consumers", context="%CPU", icon="processes")
        tp.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.top = BarList(tp.content, rows=8, empty_text="No processes available")
        self.top.pack(fill="x")
        al = Panel(side, title="Active alerts", icon="bell")
        al.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.alerts = AlertList(al.content, limit=7)
        self.alerts.pack(fill="both", expand=True)

    def update_state(self, s):
        self._state = s
        for key, tile in self.tiles.items():
            v = getattr(s, key)
            tile.set("—" if v is None else f"{v:.1f}", sub="last 2 min",
                     color=level_color(v) if v is not None and v >= 75 else None)
        self.top.set_items([(r.name, r.cpu) for r in s.top_processes])
        self.alerts.set_alerts(s.alerts)
        self.grid_plot.update(s.history, s.timestamp, {"cpu": s.avg_cpu, "ram": s.avg_ram})
        self.chart.redraw()
