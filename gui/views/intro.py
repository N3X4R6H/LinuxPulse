import platform
import socket
import time
import tkinter as tk

from visualization.plots import MemoryPie

from .. import config
from ..graph_panel import ChartPanel
from ..styles import P, FONTS
from ..widgets import LinkLabel, Panel, draw_icon, draw_logo
from .base import BaseView


def _uptime(s):
    if s is None:
        return "—"
    d, rem = divmod(int(s), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"


class IntroView(BaseView):
    title = "Introduction"
    crumb = "Project  ›  Introduction"

    def __init__(self, master, app):
        super().__init__(master, app)
        self.columnconfigure(0, weight=3, uniform="c")
        self.columnconfigure(1, weight=2, uniform="c")
        self.rowconfigure(2, weight=1)

        # ------------------------------------------------------------ project / team
        hero = Panel(self, pad=22)
        hero.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=4, pady=4)
        c = hero.content
        head = tk.Frame(c, bg=P["panel"])
        head.pack(fill="x")
        logo = tk.Canvas(head, width=64, height=64, bg=P["panel"], highlightthickness=0)
        draw_logo(logo, 32, 32, 28)
        logo.pack(side="left", padx=(0, 16))
        names = tk.Frame(head, bg=P["panel"])
        names.pack(side="left")
        tk.Label(names, text=config.APP_NAME, font=FONTS["number_md"], fg=P["text"], bg=P["panel"]).pack(anchor="w")
        tk.Label(names, text=config.APP_TAGLINE, font=FONTS["body"], fg=P["text_dim"], bg=P["panel"]).pack(anchor="w")

        tk.Frame(c, bg=P["edge"], height=1).pack(fill="x", pady=20)

        def section(text, icon):
            row = tk.Frame(c, bg=P["panel"])
            row.pack(fill="x", pady=(0, 8))
            ic = tk.Canvas(row, width=16, height=16, bg=P["panel"], highlightthickness=0)
            draw_icon(ic, icon, 8, 8, P["accent"], s=6)
            ic.pack(side="left", padx=(0, 6))
            tk.Label(row, text=text, font=FONTS["small_b"], fg=P["accent"], bg=P["panel"]).pack(side="left")

        section("Team", "system")
        tk.Label(c, text=config.TEAM_NAME, font=FONTS["h1"], fg=P["text"], bg=P["panel"]).pack(anchor="w", pady=(0, 18))

        section("Members", "tasks")
        tbl = tk.Frame(c, bg=P["edge"])
        tbl.pack(fill="x", pady=(0, 18))
        tbl.columnconfigure(1, weight=1)
        for j, h in enumerate(("#", "Name", "Roll number")):
            tk.Label(tbl, text=h, font=FONTS["small_b"], fg=P["text"], bg=P["panel_hi"], anchor="w",
                     padx=10, pady=6).grid(row=0, column=j, sticky="ew", pady=(0, 1))
        for i, (name, roll) in enumerate(config.MEMBERS, start=1):
            bg = P["panel_lo"] if i % 2 else P["panel"]
            tk.Label(tbl, text=str(i), font=FONTS["mono_sm"], fg=P["text_faint"], bg=bg, padx=10, pady=6,
                     anchor="w").grid(row=i, column=0, sticky="ew")
            tk.Label(tbl, text=name, font=FONTS["body"], fg=P["text"], bg=bg, padx=10, anchor="w"
                     ).grid(row=i, column=1, sticky="nsew")
            tk.Label(tbl, text=roll, font=FONTS["mono_sm"], fg=P["text"], bg=bg, padx=10, anchor="w"
                     ).grid(row=i, column=2, sticky="nsew")

        section("Website", "host")
        LinkLabel(c, config.WEBSITE).pack(anchor="w")

        nav = tk.Frame(c, bg=P["panel"])
        nav.pack(side="bottom", fill="x")
        for i, (key, name, desc) in enumerate((("overview", "Overview", "Gauges, per-core, live charts"),
                                               ("processes", "Processes", "Search, filter, sort tasks"),
                                               ("analytics", "Analytics", "History, averages, peaks"))):
            nav.columnconfigure(i, weight=1, uniform="n")
            self._tile(nav, key, name, desc).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))

        # ------------------------------------------------------------ clock
        clock = Panel(self, title="Local time", icon="clock")
        clock.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self.time_lbl = tk.Label(clock.content, font=FONTS["clock"], fg=P["accent"], bg=P["panel"])
        self.time_lbl.pack(anchor="w")
        self.date_lbl = tk.Label(clock.content, font=FONTS["body"], fg=P["text_dim"], bg=P["panel"])
        self.date_lbl.pack(anchor="w")

        # ------------------------------------------------------------ host (read locally via platform)
        host = Panel(self, title="Host", context="platform", icon="host")
        host.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        host.content.columnconfigure(1, weight=1)
        u = platform.uname()
        self.host_vals = {}
        for i, (k, v) in enumerate((("Hostname", socket.gethostname()), ("OS", u.system),
                                    ("Kernel", u.release), ("Arch", u.machine), ("Uptime", "—"))):
            tk.Label(host.content, text=k, font=FONTS["small"], fg=P["text_dim"], bg=P["panel"], anchor="w"
                     ).grid(row=i, column=0, sticky="w", pady=1)
            lbl = tk.Label(host.content, text=v or "—", font=FONTS["mono_sm"], fg=P["text"], bg=P["panel"], anchor="e")
            lbl.grid(row=i, column=1, sticky="e")
            self.host_vals[k] = lbl

        # ------------------------------------------------------------ memory donut
        self.pie = MemoryPie()
        self.pie_chart = ChartPanel(self, self.pie, "Memory usage", "system.ram", "memory", min_h=220)
        self.pie_chart.grid(row=2, column=1, sticky="nsew", padx=4, pady=4)
        self.tick(time.localtime())

    def _tile(self, master, key, name, desc):
        bg = P["panel_hi"]
        f = tk.Frame(master, bg=bg, highlightthickness=1, highlightbackground=P["edge"], cursor="hand2")
        ic = tk.Canvas(f, width=30, height=30, bg=bg, highlightthickness=0)
        draw_icon(ic, key, 15, 15, P["accent"], s=8)
        ic.pack(side="left", padx=(10, 6), pady=10)
        txt = tk.Frame(f, bg=bg)
        txt.pack(side="left")
        t1 = tk.Label(txt, text=name, font=FONTS["body_b"], fg=P["text"], bg=bg)
        t1.pack(anchor="w")
        t2 = tk.Label(txt, text=desc, font=FONTS["tiny"], fg=P["text_dim"], bg=bg)
        t2.pack(anchor="w")
        for w in (f, ic, txt, t1, t2):
            w.bind("<Button-1>", lambda e: self.app.show(key))
        f.bind("<Enter>", lambda e: f.config(highlightbackground=P["accent_dim"]))
        f.bind("<Leave>", lambda e: f.config(highlightbackground=P["edge"]))
        return f

    def tick(self, now):
        self.time_lbl.config(text=time.strftime("%H:%M:%S", now))
        self.date_lbl.config(text=time.strftime("%A, %d %B %Y", now))

    def update_state(self, s):
        self.host_vals["Uptime"].config(text=_uptime(s.uptime_s))
        self.pie.update(s.mem_used_gib, s.mem_available_gib)
        self.pie_chart.redraw()
