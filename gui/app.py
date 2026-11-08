"""Main window: navigation rail, top bar, section header, view stack, live loop, shutdown."""
import socket
import time
import tkinter as tk

from . import config, styles
from .platform_support import MOD_LABEL, bind_shortcut, maximize, setup_app
from .controller import DataPump
from .styles import P, FONTS
from .view_state import SourceError, ViewState
from .widgets import CountBadge, PlayButton, RailButton, StatusDot, TimeRuler, Tooltip, draw_icon, draw_logo
from .views import AnalyticsView, IntroView, OverviewView, ProcessesView

NAV = (
    ("intro", "Introduction", IntroView),
    ("overview", "Overview", OverviewView),
    ("processes", "Processes", ProcessesView),
    ("analytics", "Analytics", AnalyticsView),
)


class Rail(tk.Frame):
    def __init__(self, master, on_select):
        super().__init__(master, bg=P["rail"], width=56)
        self.pack_propagate(False)
        logo = tk.Canvas(self, width=56, height=56, bg=P["rail"], highlightthickness=0)
        draw_logo(logo, 28, 28, 14)
        logo.pack(pady=(4, 8))
        tk.Frame(self, bg=P["edge"], height=1).pack(fill="x", padx=12, pady=(0, 8))
        self.buttons = {}
        for key, label, _ in NAV:
            b = RailButton(self, key, f"{label}   {MOD_LABEL}{len(self.buttons) + 1}",
                           lambda k=key: on_select(k))
            b.pack(pady=2)
            self.buttons[key] = b

    def set_active(self, key):
        for k, b in self.buttons.items():
            b.set_active(k == key)


class TopBar(tk.Frame):
    def __init__(self, master, app, source_name):
        super().__init__(master, bg=P["topbar"], height=48)
        self.pack_propagate(False)
        self.app = app
        # host
        hb = tk.Frame(self, bg=P["topbar"])
        hb.pack(side="left", padx=(14, 0))
        ic = tk.Canvas(hb, width=26, height=26, bg=P["topbar"], highlightthickness=0)
        ic.create_oval(2, 2, 24, 24, outline=P["edge_hi"])
        draw_icon(ic, "host", 13, 13, P["text"], s=6)
        ic.pack(side="left", padx=(0, 8))
        tk.Label(hb, text=socket.gethostname().upper(), font=FONTS["body_b"], fg=P["text"], bg=P["topbar"]
                 ).pack(side="left")
        if source_name:
            tk.Label(hb, text=source_name, font=FONTS["caption"], fg=P["amber"], bg=P["topbar"],
                     highlightthickness=1, highlightbackground="#6b4a12", padx=6, pady=1).pack(side="left", padx=12)

        # right side
        right = tk.Frame(self, bg=P["topbar"])
        right.pack(side="right", padx=10)
        self.status = StatusDot(right)
        self.status.pack(side="right", padx=(12, 0))
        al = tk.Frame(right, bg=P["panel"], highlightthickness=1, highlightbackground=P["edge"], cursor="hand2")
        al.pack(side="right")
        bic = tk.Canvas(al, width=18, height=18, bg=P["panel"], highlightthickness=0)
        draw_icon(bic, "bell", 9, 9, P["text_dim"], s=6)
        bic.pack(side="left", padx=(8, 4), pady=4)
        self.al_lbl = tk.Label(al, text="Alerts", font=FONTS["small"], fg=P["text_dim"], bg=P["panel"])
        self.al_lbl.pack(side="left", padx=(0, 6))
        self.crit = CountBadge(al, P["red"])
        self.crit.pack(side="left")
        self.warn = CountBadge(al, P["amber"])
        self.warn.pack(side="left", padx=(2, 8))
        for w in (al, bic):
            w.bind("<Button-1>", lambda e: app.show("processes"))
        Tooltip(al, "Critical / warning alerts — open Processes")

        # centre: play + range
        mid = tk.Frame(self, bg=P["topbar"])
        mid.pack(side="right", padx=(0, 12))
        self.play = PlayButton(mid, app.toggle_pause)
        self.play.pack(side="left")
        rng = tk.Frame(mid, bg=P["panel"], highlightthickness=1, highlightbackground=P["edge"])
        rng.pack(side="left")
        self.rng_date = tk.Label(rng, font=FONTS["small"], fg=P["text"], bg=P["panel"])
        self.rng_date.pack(side="left", padx=(10, 6), pady=5)
        self.rng_times = tk.Label(rng, font=FONTS["mono_sm"], fg=P["accent"], bg=P["panel"])
        self.rng_times.pack(side="left")
        self.rng_dur = tk.Label(rng, font=FONTS["small"], fg=P["text_dim"], bg=P["panel"])
        self.rng_dur.pack(side="left", padx=(6, 10))
        Tooltip(self.play, "Pause / resume live updates (Space)")
        self.bind("<Configure>", self._fit)

    def _fit(self, e):
        """Drop the date from the range box on narrow windows so nothing clips."""
        if e.width < 1300:
            self.rng_date.pack_forget()
            self.al_lbl.pack_forget()
        elif not self.rng_date.winfo_ismapped():
            self.rng_date.pack(side="left", padx=(10, 6), pady=5, before=self.rng_times)
            self.al_lbl.pack(side="left", padx=(0, 6), before=self.crit)

    def set_range(self, state):
        if not state or not state.history.t:
            return
        t0, t1 = state.timestamp + state.history.t[0], state.timestamp
        self.rng_date.config(text=time.strftime("%d/%m/%Y  •", time.localtime(t1)))
        self.rng_times.config(text=time.strftime("%H:%M:%S", time.localtime(t0)) + " → " +
                              time.strftime("%H:%M:%S", time.localtime(t1)))
        dur = t1 - t0
        self.rng_dur.config(text=f"•  {dur / 60:.0f}min" if dur >= 90 else f"•  {dur:.0f}s")

    def set_alerts(self, alerts):
        self.crit.set(sum(a.level == "critical" for a in alerts))
        self.warn.set(sum(a.level == "warning" for a in alerts))


class SectionHeader(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=P["bg"])
        ic = tk.Canvas(self, width=16, height=16, bg=P["bg"], highlightthickness=0)
        draw_icon(ic, "system", 8, 8, P["accent"], s=6)
        ic.pack(side="left", padx=(0, 6))
        self.crumb = tk.Label(self, font=FONTS["small_b"], fg=P["accent"], bg=P["bg"])
        self.crumb.pack(side="left", padx=(0, 16))
        self.ruler = TimeRuler(self)
        self.ruler.pack(side="left", fill="x", expand=True)


class DashboardApp:
    def __init__(self, root, source):
        self.root = root
        styles.init(root)
        root.title(config.APP_NAME)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(1440, sw - 40)}x{min(900, sh - 80)}")
        if sw <= 1600:                      # laptops (incl. 13"/14" MacBooks): start maximised
            maximize(root)
        root.minsize(1100, 700)

        self.pump = DataPump(source)
        self.latest = None
        self.last_rx = None
        self.error = None
        self.paused = False
        self.status_text, self.status_color = "CONNECTING", P["text_dim"]
        self._jobs = {}
        self.current = None

        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        self.rail = Rail(root, self.show)
        self.rail.grid(row=0, column=0, sticky="ns")
        tk.Frame(root, bg=P["edge"], width=1).grid(row=0, column=0, sticky="nse")

        main = tk.Frame(root, bg=P["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        self.topbar = TopBar(main, self, getattr(source, "display_name", ""))
        self.topbar.grid(row=0, column=0, sticky="ew")
        tk.Frame(main, bg=P["edge"], height=1).grid(row=1, column=0, sticky="ew")
        self.header = SectionHeader(main)
        self.header.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 2))

        stack = tk.Frame(main, bg=P["bg"])
        stack.grid(row=3, column=0, sticky="nsew", padx=10, pady=(2, 8))
        stack.rowconfigure(0, weight=1)
        stack.columnconfigure(0, weight=1)
        self.views = {}
        for key, _label, cls in NAV:
            v = cls(stack, self)
            v.grid(row=0, column=0, sticky="nsew")
            self.views[key] = v

        for i, (key, *_r) in enumerate(NAV, start=1):
            bind_shortcut(root, f"Key-{i}", lambda e, k=key: self.show(k))
        root.bind("<space>", lambda e: None if isinstance(e.widget, tk.Entry) else self.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.shutdown)
        setup_app(root, config.APP_NAME, self.shutdown)

        self.show("intro")
        self.pump.start()
        self._schedule("poll", config.POLL_MS, self._poll)
        self._schedule("clock", 0, self._clock)

    # ---------------------------------------------------------------- navigation / controls
    def show(self, key):
        if key == self.current:
            return
        self.current = key
        view = self.views[key]
        view.tkraise()
        self.rail.set_active(key)
        self.header.crumb.config(text=view.crumb)
        view.on_show()
        if self.latest is not None:
            view.update_state(self.latest)

    def toggle_pause(self):
        self.paused = not self.paused
        self.topbar.play.set(not self.paused)
        if not self.paused and self.latest is not None:
            self._apply(self.latest)
        self._update_status()

    # ---------------------------------------------------------------- loops
    def _schedule(self, name, ms, fn):
        self._jobs[name] = self.root.after(ms, fn)

    def _apply(self, state):
        self.views[self.current].update_state(state)
        self.topbar.set_range(state)
        self.topbar.set_alerts(state.alerts)

    def _poll(self):
        item = self.pump.drain()
        if isinstance(item, SourceError):
            self.error = item.message
        elif isinstance(item, ViewState):
            self.last_rx, self.error = time.monotonic(), None
            self.latest = item
            if not self.paused:
                self._apply(item)
        self._update_status()
        self._schedule("poll", config.POLL_MS, self._poll)

    def _update_status(self):
        if self.error:
            text, col = "SOURCE ERROR", P["red"]
        elif self.paused:
            text, col = "PAUSED", P["amber"]
        elif self.last_rx is None:
            text, col = "CONNECTING", P["text_dim"]
        elif time.monotonic() - self.last_rx > config.STALE_AFTER_S:
            text, col = "STALE", P["amber"]
        else:
            text, col = "LIVE", P["accent"]
        self.status_text, self.status_color = text, col
        self.topbar.status.set(text, col)

    def _clock(self):
        now = time.time()
        if not self.paused:
            self.header.ruler.render(now)
        self.views[self.current].tick(time.localtime(now))
        self._schedule("clock", 1000 - int(time.time() * 1000) % 1000, self._clock)

    # ---------------------------------------------------------------- shutdown
    def shutdown(self):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        for job in self._jobs.values():
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._jobs.clear()
        self.pump.stop()
        self.root.quit()
        self.root.destroy()
