"""Dashboard GUI (Dhiren) — dark Tkinter dashboard for the Unix System Monitor.

Views: Overview · Processes · Analytics (+ About). Charts come from ``visualization.plots``
and are embedded with FigureCanvasTkAgg; the process table is ``gui.process_table``.

Integration contract (details in docs/gui_design.md):

    updates = queue.Queue()
    Dashboard(root, updates, on_close=controller.stop, source_name="")
    # controller thread: updates.put(ViewState(...))   or   updates.put(SourceError("..."))

The GUI never blocks: it drains the queue every POLL_MS with ``root.after`` and touches
widgets only on the Tk main thread. ``None`` in any ViewState field means "unavailable"
and is shown as "—", never as zero.
"""
import math
import os
import platform
import queue
import socket
import sys
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import font as tkfont
from typing import Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from visualization.plots import AnalyticsGrid, MemoryPie, StackedAreaPlot

from .process_table import ProcessTable


# ============================================================================
# Platform support (Linux / macOS)
# ============================================================================
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Primary shortcut modifier: Cmd on macOS, Ctrl elsewhere.
MOD = "Command" if IS_MAC else "Control"
MOD_LABEL = "⌘" if IS_MAC else "Ctrl+"


def bind_shortcut(root, key, callback):
    """Bind <MOD-key>; on macOS also accept Ctrl so both habits work."""
    root.bind_all(f"<{MOD}-{key}>", callback)
    if IS_MAC:
        root.bind_all(f"<Control-{key}>", callback)


def font_scale(root):
    """Factor that makes point sizes render at the same pixel size everywhere.

    Tk on X11 typically runs at 96 dpi (scaling ≈ 1.33 px/pt) while Aqua Tk uses
    72 dpi (1.0 px/pt), so fonts look ~25% smaller on a Mac without this. Never
    shrinks (HiDPI Linux keeps its larger scaling).
    """
    try:
        scaling = float(root.tk.call("tk", "scaling"))
    except (tk.TclError, ValueError):
        return 1.0
    return max(1.0, min(1.5, (96 / 72) / scaling)) if scaling > 0 else 1.0


def maximize(root):
    """Start maximised on small screens. Silently ignored where unsupported."""
    for attempt in (lambda: root.state("zoomed"),                 # macOS (Aqua), Windows
                    lambda: root.attributes("-zoomed", True)):    # X11 window managers
        try:
            attempt()
            return
        except tk.TclError:
            continue


def setup_app(root, app_name, on_quit):
    """Platform integration: macOS app menu / Cmd+Q, Linux WM class already set by tk.Tk(className=...)."""
    if IS_MAC:
        try:
            # Cmd+Q and the app menu "Quit" go through our clean shutdown
            root.createcommand("tk::mac::Quit", on_quit)
            # Minimal menubar so the app menu shows the app name instead of "Python"
            menubar = tk.Menu(root)
            app_menu = tk.Menu(menubar, name="apple")
            menubar.add_cascade(menu=app_menu)
            app_menu.add_command(label=f"About {app_name}", state="disabled")
            root.config(menu=menubar)
        except tk.TclError:
            pass


def tk_version_warning():
    """Return a warning string when the Tk build is too old for this UI, else None."""
    if tk.TkVersion < 8.6:
        hint = ("Install Python from python.org or `brew install python python-tk` — "
                "the Xcode/system Python ships Tk 8.5." if IS_MAC else
                "Install your distro's python3-tk package (Tk 8.6+).")
        return f"Tk {tk.TkVersion} detected; Tk 8.6+ is required for correct rendering. {hint}"
    return None


# ============================================================================
# View model — integration contract
# ============================================================================
# top's %Cpu(s) fields: us sy ni wa hi si st (+ id)
CPU_DIMS = ("user", "system", "nice", "iowait", "irq", "softirq", "steal")


@dataclass
class CpuBreakdown:
    user: Optional[float] = None
    system: Optional[float] = None
    nice: Optional[float] = None
    iowait: Optional[float] = None
    irq: Optional[float] = None
    softirq: Optional[float] = None
    steal: Optional[float] = None
    idle: Optional[float] = None

    @property
    def total(self) -> Optional[float]:
        return None if self.idle is None else max(0.0, min(100.0, 100.0 - self.idle))


@dataclass
class ProcessRow:
    pid: Optional[int]
    name: Optional[str]           # COMMAND
    cpu: Optional[float]          # %CPU
    mem: Optional[float]          # %MEM
    state: Optional[str]          # S: R, S, D, I, Z, T
    user: Optional[str] = None    # USER
    res_mib: Optional[float] = None   # RES
    time_s: Optional[float] = None    # TIME+ in seconds
    gpu: Optional[float] = None       # only with a separate GPU telemetry source
    is_system: Optional[bool] = None  # per collector's agreed classification


@dataclass
class Alert:
    level: str        # "warning" | "critical"
    message: str
    timestamp: float  # epoch seconds


@dataclass
class History:
    """Equal-length series. ``t`` is seconds relative to ``ViewState.timestamp`` (<= 0)."""
    t: List[float] = field(default_factory=list)
    cpu: List[Optional[float]] = field(default_factory=list)
    ram: List[Optional[float]] = field(default_factory=list)
    swap: List[Optional[float]] = field(default_factory=list)
    load1: List[Optional[float]] = field(default_factory=list)
    cpu_dims: Dict[str, List[Optional[float]]] = field(default_factory=dict)   # key in CPU_DIMS
    per_core: List[Optional[List[Optional[float]]]] = field(default_factory=list)  # per sample: core totals
    mem_used: List[Optional[float]] = field(default_factory=list)        # GiB
    mem_buffcache: List[Optional[float]] = field(default_factory=list)   # GiB
    mem_free: List[Optional[float]] = field(default_factory=list)        # GiB


@dataclass
class ViewState:
    timestamp: float
    # CPU
    cpu: Optional[float] = None
    cpu_dims: Optional[CpuBreakdown] = None
    per_core: Optional[List[CpuBreakdown]] = None
    load: Optional[Tuple[float, float, float]] = None   # 1, 5, 15 min
    # memory (GiB)
    ram: Optional[float] = None
    mem_total_gib: Optional[float] = None
    mem_used_gib: Optional[float] = None
    mem_free_gib: Optional[float] = None
    mem_buffcache_gib: Optional[float] = None
    mem_available_gib: Optional[float] = None
    swap: Optional[float] = None
    swap_used_gib: Optional[float] = None
    swap_total_gib: Optional[float] = None
    # tasks
    total: Optional[int] = None
    running: Optional[int] = None
    sleeping: Optional[int] = None
    stopped: Optional[int] = None
    zombie: Optional[int] = None
    processes: List[ProcessRow] = field(default_factory=list)
    gpu_available: bool = False
    # analytics
    history: History = field(default_factory=History)
    avg_cpu: Optional[float] = None
    avg_ram: Optional[float] = None
    peak_cpu: Optional[float] = None
    peak_ram: Optional[float] = None
    peak_swap: Optional[float] = None
    top_processes: List[ProcessRow] = field(default_factory=list)          # by %CPU
    top_memory_processes: List[ProcessRow] = field(default_factory=list)   # by %MEM
    alerts: List[Alert] = field(default_factory=list)
    n_cpus: Optional[int] = None      # logical CPUs, if known without per-core data
    # meta
    uptime_s: Optional[float] = None
    interval_s: Optional[float] = None
    hostname: Optional[str] = None

    @property
    def cores(self) -> Optional[int]:
        return len(self.per_core) if self.per_core else self.n_cpus


@dataclass
class SourceError:
    """Put on the queue by the data pump when the source thread fails."""
    message: str


# ============================================================================
# GUI settings
# ============================================================================
APP_NAME = "LinuxPulse"
APP_TAGLINE = "Real-time Linux telemetry · processes · analytics"
TEAM_NAME = "Mentally Unstable"
MEMBERS = [               # (name, roll number) — fill in
    ("Ankush Tarafdar", "MC25BT011"),
    ("Atharv Saxena", "CS25BT004"),
    ("Manish Pravin Patil", "MC25BT028"),
    ("Chettupelly Dhiren", "MC25BT005"),
    ("Pavan", "MC25BT004"),
]
WEBSITE = "https://github.com/N3X4R6H/LinuxPulse.git"   # e.g. "https://github.com/<user>/<repo>" — becomes a clickable link

# GUI timing
POLL_MS = 250          # how often the GUI drains the update queue
STALE_AFTER_S = 5.0    # no new data for this long -> status "STALE"

# Display-only thresholds (alerts themselves come from the analytics engine)
HIGH_CPU_MIN = 1.0     # % — "High CPU" filter hides idle processes


# ============================================================================
# Theme: palette, fonts, ttk styles
# ============================================================================
P = {
    "bg": "#1c1e22",          # page
    "rail": "#131417",        # left navigation rail
    "topbar": "#16171a",
    "panel": "#23262a",       # cards / chart panels
    "panel_hi": "#2b2e33",    # inputs, header rows
    "panel_lo": "#1f2125",    # table stripes
    "edge": "#32353a",
    "edge_hi": "#4a4f56",
    "track": "#383c42",       # gauge / bar track
    "text": "#e8eaed",
    "text_dim": "#9aa0a6",
    "text_faint": "#6a7077",
    "accent": "#00d26a",      # primary green
    "accent_mid": "#00ab44",
    "accent_dim": "#0f5a33",
    "accent_glow": "#17311f",
    "blue": "#3b8fe0",
    "cyan": "#2ec4e6",
    "teal": "#1fb39a",
    "amber": "#f5a623",
    "yellow": "#f2c94c",
    "red": "#f0485b",
    "violet": "#8f7cf7",
    "grid": "#2f3237",
}

# CPU dimension colours (stack order bottom -> top)
CPU_COLORS = {
    "user": "#1f7ab8", "system": "#e0475b", "nice": "#b065d1", "iowait": "#25c2a0",
    "irq": "#7a6ff0", "softirq": "#f2b134", "steal": "#5a6b7d",
}
MEM_COLORS = {"used": "#1f7ab8", "buffcache": "#25a882", "free": "#3c4148"}
SERIES_COLORS = {"cpu": P["accent"], "ram": P["blue"], "swap": P["violet"], "load1": P["amber"]}

# Palette handed to the stand-alone ProcessTable component
TABLE_COLORS = {k: P[k] for k in ("panel", "panel_hi", "panel_lo", "edge", "edge_hi", "text", "text_dim",
                                  "text_faint", "accent", "accent_mid", "red", "amber", "violet")}
TABLE_COLORS["selected"] = "#2c3d33"


def table_fonts():
    return {"row": FONTS["mono_sm"], "heading": FONTS["small_b"], "empty": FONTS["body"]}


WARN_LEVEL = 75.0
CRIT_LEVEL = 90.0


def level_color(pct):
    if pct is None:
        return P["text_faint"]
    if pct >= CRIT_LEVEL:
        return P["red"]
    if pct >= WARN_LEVEL:
        return P["amber"]
    return P["accent"]


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


# Preference order covers Linux distros and macOS (SF / Helvetica Neue / Menlo).
_SANS = ("IBM Plex Sans", "Inter", "SF Pro Text", "SF Pro", "Helvetica Neue", "Ubuntu", "Cantarell",
         "Noto Sans", "DejaVu Sans", "Helvetica")
_MONO = ("IBM Plex Mono", "JetBrains Mono", "SF Mono", "Menlo", "Monaco", "Ubuntu Mono",
         "DejaVu Sans Mono", "Liberation Mono", "Courier")
FONTS = {}
FAMILIES = {}


def _pick(cands, avail):
    for f in cands:
        if f in avail:
            return f
    return cands[-1]


def init_styles(root):
    avail = set(tkfont.families(root))
    sans, mono = _pick(_SANS, avail), _pick(_MONO, avail)
    FAMILIES.update(sans=sans, mono=mono)
    spec = {
        "h1": (sans, 13, "bold"),
        "title": (sans, 10, "normal"),
        "body": (sans, 10, "normal"),
        "body_b": (sans, 10, "bold"),
        "small": (sans, 9, "normal"),
        "small_b": (sans, 9, "bold"),
        "caption": (sans, 8, "bold"),
        "tiny": (sans, 8, "normal"),
        "gauge": (sans, 19, "bold"),
        "number": (sans, 30, "bold"),
        "number_md": (sans, 20, "bold"),
        "legend_val": (sans, 12, "bold"),
        "mono": (mono, 10, "normal"),
        "mono_sm": (mono, 9, "normal"),
        "mono_b": (mono, 10, "bold"),
        "clock": (mono, 30, "bold"),
    }
    scale = font_scale(root)
    for k, (fam, size, weight) in spec.items():
        FONTS[k] = tkfont.Font(root=root, family=fam, size=round(size * scale), weight=weight)
    root.configure(bg=P["bg"])
    root.option_add("*Font", FONTS["body"])


# ============================================================================
# Reusable widgets
# ============================================================================
def fmt_pct(v, nd=1):
    return "—" if v is None else f"{v:.{nd}f}%"


def fmt_gib(v):
    return "—" if v is None else f"{v:.2f}"


def round_rect(c, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, splinesteps=12, **kw)


# ============================================================================ icons
def draw_icon(c, name, cx, cy, color, s=9):
    """Small line icons, roughly 2*s across, centred at (cx, cy)."""
    w = 2 if s >= 8 else 1.5
    if name == "intro":
        pts = []
        for k in range(6):
            a = math.radians(90 + k * 60)
            pts += [cx + s * math.cos(a), cy - s * math.sin(a)]
        c.create_polygon(pts, outline=color, fill="", width=w)
        c.create_line(cx, cy - s * .1, cx, cy + s * .5, fill=color, width=w)
        c.create_oval(cx - 1.3, cy - s * .55, cx + 1.3, cy - s * .3, fill=color, outline="")
    elif name == "overview":
        q, g = s * .8, s * .3
        for dx in (-1, 1):
            for dy in (-1, 1):
                x0 = cx + (g / 2 if dx > 0 else -g / 2 - q)
                y0 = cy + (g / 2 if dy > 0 else -g / 2 - q)
                c.create_rectangle(x0, y0, x0 + q, y0 + q, outline=color, width=w)
    elif name == "processes":
        for dy in (-s * .6, 0, s * .6):
            c.create_rectangle(cx - s, cy + dy - 1, cx - s + 2.5, cy + dy + 1.5, fill=color, outline="")
            c.create_line(cx - s + 5, cy + dy, cx + s, cy + dy, fill=color, width=w)
    elif name == "analytics":
        c.create_line(cx - s, cy - s, cx - s, cy + s, cx + s, cy + s, fill=color, width=w)
        c.create_line(cx - s * .6, cy + s * .4, cx - s * .15, cy - s * .2, cx + s * .2, cy + s * .2,
                      cx + s, cy - s * .6, fill=color, width=w)
    elif name == "cpu":
        c.create_rectangle(cx - s * .6, cy - s * .6, cx + s * .6, cy + s * .6, outline=color, width=w)
        c.create_rectangle(cx - s * .25, cy - s * .25, cx + s * .25, cy + s * .25, fill=color, outline="")
        for k in (-.3, .3):
            for a, b in ((cx + s * k, cy - s), (cx + s * k, cy + s * .6)):
                c.create_line(a, b, a, b + s * .4, fill=color, width=1)
            for a, b in ((cx - s, cy + s * k), (cx + s * .6, cy + s * k)):
                c.create_line(a, b, a + s * .4, b, fill=color, width=1)
    elif name == "memory":
        c.create_rectangle(cx - s, cy - s * .45, cx + s, cy + s * .45, outline=color, width=w)
        for k in (-.5, 0, .5):
            c.create_line(cx + s * k, cy + s * .45, cx + s * k, cy + s * .8, fill=color, width=1)
            c.create_rectangle(cx + s * k - 1.5, cy - s * .15, cx + s * k + 1.5, cy + s * .15, fill=color, outline="")
    elif name == "swap":
        c.create_line(cx - s, cy - s * .35, cx + s * .8, cy - s * .35, arrow="last", arrowshape=(4, 5, 2),
                      fill=color, width=w)
        c.create_line(cx + s, cy + s * .35, cx - s * .8, cy + s * .35, arrow="last", arrowshape=(4, 5, 2),
                      fill=color, width=w)
    elif name == "load":
        c.create_arc(cx - s, cy - s, cx + s, cy + s, start=0, extent=180, style="arc", outline=color, width=w)
        c.create_line(cx, cy + s * .2, cx + s * .55, cy - s * .5, fill=color, width=w)
    elif name == "tasks":
        for i, dy in enumerate((-s * .6, 0, s * .6)):
            c.create_oval(cx - s, cy + dy - 2, cx - s + 4, cy + dy + 2, outline=color)
            c.create_line(cx - s + 6, cy + dy, cx + s, cy + dy, fill=color, width=w)
    elif name == "host":
        for dy in (-s * .5, s * .5):
            c.create_rectangle(cx - s, cy + dy - s * .4, cx + s, cy + dy + s * .4, outline=color, width=w)
            c.create_oval(cx + s * .5, cy + dy - 1.2, cx + s * .5 + 2.4, cy + dy + 1.2, fill=color, outline="")
    elif name == "bell":
        c.create_arc(cx - s * .7, cy - s, cx + s * .7, cy + s * .6, start=0, extent=180, style="arc",
                     outline=color, width=w)
        c.create_line(cx - s * .7, cy - s * .2, cx - s * .7, cy + s * .45, cx + s * .7, cy + s * .45,
                      cx + s * .7, cy - s * .2, fill=color, width=w)
        c.create_line(cx - s, cy + s * .5, cx + s, cy + s * .5, fill=color, width=w)
        c.create_oval(cx - 1.5, cy + s * .65, cx + 1.5, cy + s * .95, fill=color, outline="")
    elif name == "clock":
        c.create_oval(cx - s, cy - s, cx + s, cy + s, outline=color, width=w)
        c.create_line(cx, cy - s * .6, cx, cy, cx + s * .45, cy + s * .3, fill=color, width=w)
    elif name == "system":
        for k in range(8):
            a = math.radians(k * 45)
            r = s * .85
            c.create_oval(cx + r * math.cos(a) - 1.6, cy + r * math.sin(a) - 1.6,
                          cx + r * math.cos(a) + 1.6, cy + r * math.sin(a) + 1.6, fill=color, outline="")
        c.create_oval(cx - s * .35, cy - s * .35, cx + s * .35, cy + s * .35, outline=color, width=w)


def draw_logo(c, cx, cy, s, color=P["accent"]):
    """Rounded square mark with a pulse trace."""
    round_rect(c, cx - s, cy - s, cx + s, cy + s, s * .45, fill=color, outline="")
    u = s / 10
    c.create_line(cx - 7 * u, cy + u, cx - 3 * u, cy + u, cx - 1.2 * u, cy - 4.5 * u, cx + 1.5 * u, cy + 5 * u,
                  cx + 3.4 * u, cy + u, cx + 7 * u, cy + u, fill=P["rail"], width=max(2, s / 7),
                  joinstyle="round", capstyle="round")


# ============================================================================ panel
class Panel(tk.Frame):
    """Flat bordered panel with an optional title row (icon · title · context)."""

    def __init__(self, master, title=None, context=None, icon=None, pad=12, hover=False, bg=None):
        bg = bg or P["panel"]
        super().__init__(master, bg=bg, highlightthickness=1, highlightbackground=P["edge"],
                         highlightcolor=P["edge"])
        self.header_right = None
        if title:
            hdr = tk.Frame(self, bg=bg)
            hdr.pack(fill="x", padx=pad, pady=(pad - 2, 6))
            if icon:
                ic = tk.Canvas(hdr, width=16, height=16, bg=bg, highlightthickness=0)
                draw_icon(ic, icon, 8, 8, P["text_dim"], s=6)
                ic.pack(side="left", padx=(0, 7))
            tk.Label(hdr, text=title, font=FONTS["title"], fg=P["text"], bg=bg).pack(side="left")
            if context:
                tk.Label(hdr, text=f"·  {context}", font=FONTS["mono_sm"], fg=P["text_faint"],
                         bg=bg).pack(side="left", padx=(8, 0))
            self.header_right = tk.Frame(hdr, bg=bg)
            self.header_right.pack(side="right")
        self.content = tk.Frame(self, bg=bg)
        self.content.pack(fill="both", expand=True, padx=pad, pady=(0 if title else pad, pad))
        if hover:
            self._hov = False
            self.bind("<Enter>", self._chk, add="+")
            self.bind("<Leave>", self._chk, add="+")

    def _chk(self, _e=None):
        self.after_idle(self._upd)

    def _upd(self):
        try:
            px, py = self.winfo_pointerxy()
            x, y = self.winfo_rootx(), self.winfo_rooty()
            inside = x <= px < x + self.winfo_width() and y <= py < y + self.winfo_height()
        except tk.TclError:
            return
        if inside != self._hov:
            self._hov = inside
            self.config(highlightbackground=P["edge_hi"] if inside else P["edge"])


# ============================================================================ gauges & cards
class RingGauge(tk.Canvas):
    """Full-circle gauge: value arc (clockwise from 12 o'clock), dim peak arc, centred readout."""

    def __init__(self, master, size=150, unit="%"):
        super().__init__(master, width=size, height=size, bg=master.cget("bg"), highlightthickness=0)
        self.size, self.unit = size, unit
        self.value = self.peak = None
        self._shown, self._target, self._job = 0.0, 0.0, None
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, peak=None):
        self.value, self.peak = value, peak
        self._target = 0.0 if value is None else max(0.0, min(100.0, float(value)))
        if self._job is None:
            self._animate()

    def _animate(self):
        d = self._target - self._shown
        if abs(d) < 0.05:
            self._shown, self._job = self._target, None
            self._draw()
            return
        self._shown += d * 0.25
        self._draw()
        self._job = self.after(16, self._animate)

    def destroy(self):
        if self._job:
            self.after_cancel(self._job)
        super().destroy()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20:
            w = h = self.size
        s = min(w, h)
        th = max(10, s * .13)
        r = s / 2 - th / 2 - 2
        cx, cy = w / 2, h / 2
        box = (cx - r, cy - r, cx + r, cy + r)
        self.create_oval(*box, outline=P["track"], width=th)
        if self.value is not None:
            col = level_color(self._shown)
            if self._shown > 0.1:
                self.create_arc(*box, start=90, extent=-min(359.9, 360 * self._shown / 100), style="arc",
                                width=th, outline=col)
            if self.peak is not None:   # peak-in-window marker: short radial tick across the ring
                a = math.radians(90 - 360 * min(100.0, self.peak) / 100)
                r1, r2 = r - th / 2 - 3, r + th / 2 + 3
                self.create_line(cx + r1 * math.cos(a), cy - r1 * math.sin(a), cx + r2 * math.cos(a),
                                 cy - r2 * math.sin(a), fill=P["red"], width=2)
            txt = f"{self._shown:.1f}" if self._shown < 99.95 else "100"
            self.create_text(cx, cy - 6, text=txt, fill=P["text"], font=FONTS["gauge"])
            self.create_text(cx, cy + 16, text=self.unit, fill=P["text_dim"], font=FONTS["small"])
        else:
            self.create_text(cx, cy - 6, text="—", fill=P["text_faint"], font=FONTS["gauge"])
            self.create_text(cx, cy + 16, text="unavailable", fill=P["text_faint"], font=FONTS["small"])


class GaugeCard(Panel):
    def __init__(self, master, title, icon=None, size=124):
        super().__init__(master, title=title, icon=icon, hover=True, pad=10)
        self.gauge = RingGauge(self.content, size=size)
        self.gauge.pack(fill="both", expand=True)
        self.detail = tk.Label(self.content, text="—", font=FONTS["mono_sm"], fg=P["text_dim"], bg=P["panel"])
        self.detail.pack(pady=(6, 0))

    def set(self, pct, peak=None, detail=""):
        self.gauge.set(pct, peak)
        self.detail.config(text=detail or "—")


class NumberCard(Panel):
    """Big centred number with unit and a secondary line (Netdata-style number tile)."""

    def __init__(self, master, title, unit="", icon=None, big=True, pad=10):
        super().__init__(master, title=title, icon=icon, hover=True, pad=pad)
        mid = tk.Frame(self.content, bg=P["panel"])
        mid.pack(expand=True)
        row = tk.Frame(mid, bg=P["panel"])
        row.pack()
        self.value = tk.Label(row, text="—", font=FONTS["number" if big else "number_md"],
                              fg=P["text_faint"], bg=P["panel"])
        self.value.pack(side="left")
        self.unit = tk.Label(row, text=unit, font=FONTS["body_b"], fg=P["text_dim"], bg=P["panel"])
        self.unit.pack(side="left", anchor="s", padx=(4, 0), pady=(0, 8 if big else 4))
        self.sub = tk.Label(mid, text="", font=FONTS["mono_sm"], fg=P["text_dim"], bg=P["panel"], justify="center")
        self.sub.pack(pady=(2, 0))
        self.content.bind("<Configure>", lambda e: self.sub.config(wraplength=max(60, e.width - 8)), add="+")

    def set(self, text, sub=None, color=None):
        self.value.config(text=text, fg=color or (P["text"] if text != "—" else P["text_faint"]))
        if not hasattr(self, "_unit_text"):
            self._unit_text = self.unit.cget("text")
        self.unit.config(text="" if text == "—" else self._unit_text)
        if sub is not None:
            self.sub.config(text=sub)


class PerCoreBars(tk.Canvas):
    """One stacked bar per logical CPU (user / system / other), laid out in columns."""
    ROW_H, MIN_COL_W = 22, 250
    TILE_W, TILE_H, TILE_THRESHOLD = 74, 30, 16   # many cores -> compact heat tiles
    SEGMENTS = (("user", P["blue"]), ("system", P["red"]), ("other", P["amber"]))

    def __init__(self, master):
        super().__init__(master, width=200, height=self.ROW_H + 4, bg=master.cget("bg"), highlightthickness=0)
        self.cores = None
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, cores):
        self.cores = cores
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 50:
            return
        if not self.cores:
            self.create_text(4, self.ROW_H / 2 + 2, anchor="w", fill=P["text_faint"], font=FONTS["small"],
                             text="Per-CPU data not provided by this data source (Linux top -1 reports it; macOS top does not).")
            return
        n = len(self.cores)
        if n > self.TILE_THRESHOLD:
            self._draw_tiles(w)
            return
        cols = max(1, min(n, int(w // self.MIN_COL_W), 4))
        rows = math.ceil(n / cols)
        need = rows * self.ROW_H + 4
        if int(self.cget("height")) != need:
            self.config(height=need)
        cw = w / cols
        for i, core in enumerate(self.cores):
            col, row = divmod(i, rows)
            x0, y = col * cw, 2 + row * self.ROW_H
            mid = y + self.ROW_H / 2
            self.create_text(x0 + 2, mid, anchor="w", text=f"cpu{i}", fill=P["text_dim"], font=FONTS["mono_sm"])
            bx0, bx1 = x0 + 48, x0 + cw - 66
            self.create_rectangle(bx0, mid - 4, bx1, mid + 4, fill=P["track"], outline="")
            total = core.total
            if total is None:
                self.create_text(x0 + cw - 12, mid, anchor="e", text="—", fill=P["text_faint"], font=FONTS["mono_sm"])
                continue
            other = sum(v or 0 for v in (core.nice, core.iowait, core.irq, core.softirq, core.steal))
            parts = {"user": core.user or 0, "system": core.system or 0, "other": other}
            x = bx0
            for key, col_ in self.SEGMENTS:
                dx = (bx1 - bx0) * min(parts[key], 100) / 100
                if dx > 0.5:
                    self.create_rectangle(x, mid - 4, min(bx1, x + dx), mid + 4, fill=col_, outline="")
                x += dx
            self.create_text(x0 + cw - 12, mid, anchor="e", text=f"{total:5.1f}%",
                             fill=level_color(total) if total >= 75 else P["text"], font=FONTS["mono_sm"])


    def _draw_tiles(self, w):
        n = len(self.cores)
        cols = max(1, int((w + 4) // (self.TILE_W + 4)))
        rows = math.ceil(n / cols)
        need = rows * (self.TILE_H + 4)
        if int(self.cget("height")) != need:
            self.config(height=need)
        tw = (w - (cols - 1) * 4) / cols
        for i, core in enumerate(self.cores):
            r, c = divmod(i, cols)
            x, y = c * (tw + 4), r * (self.TILE_H + 4)
            t = core.total
            fill = P["panel_lo"] if t is None else blend(P["panel_lo"], level_color(t), 0.12 + 0.5 * t / 100)
            self.create_rectangle(x, y, x + tw, y + self.TILE_H, fill=fill, outline=P["edge"])
            self.create_text(x + 6, y + 9, anchor="w", text=f"cpu{i}", fill=P["text_dim"], font=FONTS["tiny"])
            self.create_text(x + tw - 6, y + self.TILE_H - 10, anchor="e",
                             text="—" if t is None else f"{t:.0f}%", fill=P["text"], font=FONTS["small_b"])


def legend_chips(master, items):
    """Static legend: [(label, colour), ...] packed right-to-left into ``master``."""
    bg = master.cget("bg")
    for label, color in reversed(items):
        tk.Label(master, text=label, font=FONTS["tiny"], fg=P["text_dim"], bg=bg).pack(side="right", padx=(3, 10))
        tk.Frame(master, bg=color, width=9, height=9).pack(side="right")


class DimensionLegend(tk.Frame):
    """Netdata-style legend under a chart. Click an item to hide/show that dimension."""

    def __init__(self, master, dims, unit, on_toggle=None):
        super().__init__(master, bg=master.cget("bg"))
        self.unit, self.on_toggle = unit, on_toggle
        self.hidden = set()
        self.items = {}
        bg = self.cget("bg")
        self._order = []
        for key, label, color in dims:
            it = tk.Frame(self, bg=bg, cursor="hand2")
            self._order.append(it)
            bar = tk.Frame(it, bg=color, width=3)
            bar.pack(side="left", fill="y", padx=(0, 7))
            inner = tk.Frame(it, bg=bg)
            inner.pack(side="left")
            lab = tk.Label(inner, text=label, font=FONTS["tiny"], fg=P["text_dim"], bg=bg)
            lab.pack(anchor="w")
            row = tk.Frame(inner, bg=bg)
            row.pack(anchor="w")
            val = tk.Label(row, text="—", font=FONTS["legend_val"], fg=P["text"], bg=bg)
            val.pack(side="left")
            un = tk.Label(row, text=unit, font=FONTS["tiny"], fg=P["text_faint"], bg=bg)
            un.pack(side="left", anchor="s", padx=(3, 0), pady=(0, 3))
            self.items[key] = (bar, lab, val, color)
            for wdg in (it, bar, inner, lab, row, val, un):
                wdg.bind("<Button-1>", lambda e, k=key: self.toggle(k))

        self._cols = None
        self.bind("<Configure>", self._reflow)
        self.after_idle(lambda: self._reflow(None))

    def _reflow(self, e):
        """Grid items in as many columns as fit; wraps onto extra rows when narrow."""
        width = self.winfo_width() if e is None else e.width
        item_w = max(w.winfo_reqwidth() for w in self._order) + 8
        cols = max(1, min(len(self._order), int(width // item_w))) if width > 1 else len(self._order)
        if cols == self._cols:
            return
        self._cols = cols
        for i, it in enumerate(self._order):
            r, c = divmod(i, cols)
            it.grid(row=r, column=c, sticky="w", padx=(0, 8), pady=(0 if r == 0 else 6, 0))

    def toggle(self, key):
        self.hidden ^= {key}
        bar, lab, val, color = self.items[key]
        off = key in self.hidden
        bar.config(bg=P["edge"] if off else color)
        val.config(fg=P["text_faint"] if off else P["text"])
        lab.config(fg=P["text_faint"] if off else P["text_dim"])
        if self.on_toggle:
            self.on_toggle(set(self.hidden))

    def set_values(self, values, fmt="{:.2f}"):
        for key, (bar, lab, val, color) in self.items.items():
            v = values.get(key)
            val.config(text="—" if v is None else fmt.format(v))


# ============================================================================ index (right column)
class IndexPanel(Panel):
    """Metric index: sections of label · value · mini bar (like Netdata's right-hand index)."""

    def __init__(self, master, sections):
        """sections: [(title, icon, [(key, label), ...]), ...]"""
        super().__init__(master, title="Metrics index", icon="system", pad=10)
        self.rows = {}
        c = self.content
        c.columnconfigure(0, weight=1)
        r = 0
        for title, icon, items in sections:
            hdr = tk.Frame(c, bg=P["panel"])
            hdr.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10 if r else 2, 4))
            ic = tk.Canvas(hdr, width=16, height=16, bg=P["panel"], highlightthickness=0)
            draw_icon(ic, icon, 8, 8, P["accent"], s=6)
            ic.pack(side="left", padx=(0, 6))
            tk.Label(hdr, text=title, font=FONTS["small_b"], fg=P["accent"], bg=P["panel"]).pack(side="left")
            r += 1
            for key, label in items:
                lab = tk.Label(c, text=label, font=FONTS["small"], fg=P["text_dim"], bg=P["panel"], anchor="w")
                val = tk.Label(c, text="—", font=FONTS["mono_sm"], fg=P["text"], bg=P["panel"], anchor="e", width=8)
                bar = tk.Canvas(c, width=28, height=10, bg=P["panel"], highlightthickness=0)
                lab.grid(row=r, column=0, sticky="w", padx=(22, 0), pady=1)
                val.grid(row=r, column=1, sticky="e", padx=(4, 6))
                bar.grid(row=r, column=2, sticky="e")
                self.rows[key] = (val, bar)
                r += 1

    def set_values(self, values):
        """values: {key: (text, fraction 0..1 or None)}"""
        for key, (val, bar) in self.rows.items():
            text, frac = values.get(key, ("—", None))
            val.config(text=text, fg=P["text"] if text != "—" else P["text_faint"])
            bar.delete("all")
            bar.create_rectangle(0, 1, 27, 9, fill=P["panel_lo"], outline=P["edge"])
            if frac:
                bar.create_rectangle(1, 2, 1 + 25 * max(0.0, min(1.0, frac)), 8, fill=P["violet"], outline="")


# ============================================================================ chrome
class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self.job = widget, text, None, None
        widget.bind("<Enter>", self._sched, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _sched(self, _e):
        self.job = self.widget.after(350, self._show)

    def _show(self):
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 4
        y = self.widget.winfo_rooty() + self.widget.winfo_height() // 2 - 12
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        try:
            self.tip.wm_attributes("-topmost", True)   # macOS: keep above the main window
        except tk.TclError:
            pass
        tk.Label(self.tip, text=self.text, font=FONTS["small"], fg=P["text"], bg=P["panel_hi"],
                 padx=8, pady=4, highlightthickness=1, highlightbackground=P["edge_hi"]).pack()

    def _hide(self, _e):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


class RailButton(tk.Canvas):
    W, H = 56, 50

    def __init__(self, master, icon, label, command):
        super().__init__(master, width=self.W, height=self.H, bg=P["rail"], highlightthickness=0, cursor="hand2")
        self.icon, self.command = icon, command
        self.active = self.hover = False
        self.bind("<Enter>", lambda e: self._h(True), add="+")
        self.bind("<Leave>", lambda e: self._h(False), add="+")
        self.bind("<Button-1>", lambda e: self.command())
        Tooltip(self, label)
        self._draw()

    def _h(self, v):
        self.hover = v
        self._draw()

    def set_active(self, v):
        self.active = v
        self._draw()

    def _draw(self):
        self.delete("all")
        if self.active or self.hover:
            round_rect(self, 9, 6, self.W - 9, self.H - 6, 7,
                       fill="#24272b" if self.active else "#1c1e21", outline=P["edge"] if self.active else "")
        if self.active:
            self.create_rectangle(0, 13, 3, self.H - 13, fill=P["accent"], outline="")
        col = P["accent"] if self.active else (P["text"] if self.hover else P["text_faint"])
        draw_icon(self, self.icon, self.W / 2, self.H / 2, col, s=8)


class TimeRuler(tk.Canvas):
    """Section header ruler: minor/major ticks, a cursor dot and the current timestamp."""

    def __init__(self, master):
        super().__init__(master, height=24, width=100, bg=master.cget("bg"), highlightthickness=0)
        self.bind("<Configure>", lambda e: self.render())

    def render(self, now=None):
        self.delete("all")
        w = self.winfo_width()
        if w < 200:
            return
        now = now or time.time()
        label = "> " + time.strftime("%d/%m/%Y•%H:%M:%S", time.localtime(now))
        tw = FONTS["mono_sm"].measure(label) + 16
        end = w - tw
        self.create_line(0, 12, end, 12, fill=P["edge"])
        x, i = 0, 0
        while x < end - 30:
            h = 4 if i % 10 == 0 else 2
            self.create_line(x, 12 - h, x, 12 + h, fill=P["edge_hi"] if i % 10 == 0 else P["edge"])
            x += 8
            i += 1
        self.create_oval(end - 28, 7, end - 18, 17, outline=P["accent"], width=1.5)
        self.create_text(w - 2, 12, anchor="e", text=label, fill=P["accent"], font=FONTS["mono_sm"])


class PlayButton(tk.Frame):
    def __init__(self, master, command):
        super().__init__(master, bg=P["accent_mid"], cursor="hand2")
        self.command = command
        self.icon = tk.Canvas(self, width=14, height=14, bg=P["accent_mid"], highlightthickness=0)
        self.icon.pack(side="left", padx=(10, 4), pady=5)
        self.lbl = tk.Label(self, text="", font=FONTS["small_b"], fg="#ffffff", bg=P["accent_mid"])
        self.lbl.pack(side="left", padx=(0, 12))
        for w in (self, self.icon, self.lbl):
            w.bind("<Button-1>", lambda e: self.command())
        self.set(True)

    def set(self, playing):
        bg = P["accent_mid"] if playing else "#8a5a10"
        for w in (self, self.icon, self.lbl):
            w.config(bg=bg)
        self.icon.delete("all")
        if playing:
            self.icon.create_polygon(3, 2, 12, 7, 3, 12, fill="#ffffff", outline="")
            self.lbl.config(text="Playing")
        else:
            self.icon.create_rectangle(3, 2, 6, 12, fill="#ffffff", outline="")
            self.icon.create_rectangle(8, 2, 11, 12, fill="#ffffff", outline="")
            self.lbl.config(text="Paused")


class CountBadge(tk.Label):
    def __init__(self, master, color):
        super().__init__(master, text="0", font=FONTS["caption"], fg="#ffffff", bg=color, padx=6, pady=1)
        self.color = color

    def set(self, n):
        self.config(text=str(n), bg=self.color if n else P["edge"], fg="#ffffff" if n else P["text_faint"])


class StatusDot(tk.Frame):
    """● TEXT status indicator."""

    def __init__(self, master):
        super().__init__(master, bg=master.cget("bg"))
        self.dot = tk.Canvas(self, width=10, height=10, bg=self.cget("bg"), highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 6))
        self.lbl = tk.Label(self, text="", font=FONTS["caption"], bg=self.cget("bg"))
        self.lbl.pack(side="left")
        self.state = None

    def set(self, text, color):
        if (text, color) == self.state:
            return
        self.state = (text, color)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=color, outline="")
        self.lbl.config(text=text, fg=color)


# ============================================================================ lists
class AlertList(tk.Frame):
    LEVELS = {"critical": ("CRITICAL", "red"), "warning": ("WARNING", "amber")}

    def __init__(self, master, limit=5, empty_text="No active alerts"):
        super().__init__(master, bg=master.cget("bg"))
        self.limit, self.empty_text, self._sig = limit, empty_text, None
        self.set_alerts([])

    def set_alerts(self, alerts):
        alerts = list(alerts)[: self.limit]
        sig = tuple((a.level, a.message, int(a.timestamp)) for a in alerts)
        if sig == self._sig:
            return
        self._sig = sig
        for ch in self.winfo_children():
            ch.destroy()
        bg = self.cget("bg")
        if not alerts:
            tk.Label(self, text="✓  " + self.empty_text, font=FONTS["small"], fg=P["accent"], bg=bg
                     ).pack(anchor="w", pady=4)
            return
        for a in alerts:
            tag, key = self.LEVELS.get(a.level, (a.level.upper(), "amber"))
            col = P[key]
            row = tk.Frame(self, bg=P["panel_lo"])
            row.pack(fill="x", pady=2)
            tk.Frame(row, bg=col, width=3).pack(side="left", fill="y")
            tk.Label(row, text=tag, font=FONTS["caption"], fg=col, bg=row.cget("bg"), width=9,
                     anchor="w").pack(side="left", padx=(8, 0), pady=5)
            tk.Label(row, text=time.strftime("%H:%M:%S", time.localtime(a.timestamp)),
                     font=FONTS["mono_sm"], fg=P["text_faint"], bg=row.cget("bg")).pack(side="right", padx=8)
            tk.Label(row, text=a.message, font=FONTS["small"], fg=P["text"], bg=row.cget("bg"), width=1,
                     anchor="w").pack(side="left", fill="x", expand=True)


class BarList(tk.Frame):
    """Ranked rows: name · bar · value."""

    def __init__(self, master, rows=5, color=P["violet"], empty_text="No data"):
        super().__init__(master, bg=master.cget("bg"))
        self.color = color
        self.columnconfigure(1, weight=1)
        bg = self.cget("bg")
        self._rows = []
        for i in range(rows):
            name = tk.Label(self, font=FONTS["mono_sm"], fg=P["text"], bg=bg, anchor="w", width=17)
            bar = tk.Canvas(self, width=40, height=10, bg=bg, highlightthickness=0)
            val = tk.Label(self, font=FONTS["mono_sm"], fg=P["text_dim"], bg=bg, anchor="e", width=7)
            name.grid(row=i, column=0, sticky="w", pady=3)
            bar.grid(row=i, column=1, sticky="ew", padx=8)
            val.grid(row=i, column=2, sticky="e")
            bar.bind("<Configure>", lambda e, k=i: self._draw(k))
            self._rows.append([name, bar, val, None])
        self.empty = tk.Label(self, text=empty_text, font=FONTS["small"], fg=P["text_faint"], bg=bg)

    def set_items(self, items):
        items = list(items)[: len(self._rows)]
        (self.empty.grid(row=0, column=0, columnspan=3, sticky="w", pady=6) if not items
         else self.empty.grid_remove())
        for i, row in enumerate(self._rows):
            if i < len(items):
                label, v = items[i]
                label = label or "—"
                row[0].config(text=label if len(label) <= 17 else label[:16] + "…")
                row[2].config(text=fmt_pct(v))
                row[3] = v
                for wdg in row[:3]:
                    wdg.grid()
            else:
                row[3] = None
                for wdg in row[:3]:
                    wdg.grid_remove()
            self._draw(i)

    def _draw(self, i):
        _, bar, _, v = self._rows[i]
        bar.delete("all")
        w = bar.winfo_width()
        bar.create_rectangle(0, 1, w - 1, 9, fill=P["panel_lo"], outline=P["edge"])
        if v is not None:
            col = level_color(v) if v >= 75 else self.color
            bar.create_rectangle(1, 2, 1 + (w - 3) * min(1.0, v / 100), 8, fill=col, outline="")


# ============================================================================ links
class LinkLabel(tk.Label):
    """Clickable URL: opens in the default browser (Linux: xdg-open, macOS: open)."""

    def __init__(self, master, url, text=None, font=None, color=P["cyan"]):
        super().__init__(master, text=text or url, font=font or FONTS["mono"], fg=color,
                         bg=master.cget("bg"), cursor="hand2")
        self.url = self.normalize(url)
        self.color = color
        self._font = tkfont.Font(font=self.cget("font"))
        self._ufont = tkfont.Font(font=self.cget("font"))
        self._ufont.configure(underline=True)
        if not self.url:
            self.config(cursor="", fg=P["text_faint"])
            return
        self.bind("<Button-1>", self.open)
        self.bind("<Enter>", lambda e: self.config(font=self._ufont, fg=blend(color, "#ffffff", .3)))
        self.bind("<Leave>", lambda e: self.config(font=self._font, fg=color))

    @staticmethod
    def normalize(url):
        """'github.com/x/y' -> 'https://github.com/x/y'; placeholders like '<...>' -> None."""
        url = (url or "").strip()
        if not url or url.startswith("<"):
            return None
        return url if "://" in url else "https://" + url

    def open(self, _e=None):
        import webbrowser
        try:
            if not webbrowser.open(self.url, new=2):
                raise webbrowser.Error("no browser available")
        except webbrowser.Error:
            # no browser registered (e.g. minimal Linux): copy the link instead
            self.clipboard_clear()
            self.clipboard_append(self.url)
            self.config(text=f"{self.url}   (copied to clipboard)")


# ============================================================================ inputs
class TabControl(tk.Frame):
    """Underlined text tabs (used for process filters)."""

    def __init__(self, master, options, command, initial=None):
        super().__init__(master, bg=master.cget("bg"))
        self.command, self.tabs, self.value = command, {}, None
        for opt in options:
            f = tk.Frame(self, bg=self.cget("bg"), cursor="hand2")
            f.pack(side="left", padx=(0, 2))
            lbl = tk.Label(f, text=opt, font=FONTS["small_b"], padx=10, pady=5, bg=self.cget("bg"))
            lbl.pack()
            line = tk.Frame(f, height=2)
            line.pack(fill="x")
            for w in (f, lbl):
                w.bind("<Button-1>", lambda e, o=opt: self.select(o))
            self.tabs[opt] = (lbl, line)
        self.select(initial or options[0], fire=False)

    def select(self, opt, fire=True):
        self.value = opt
        for o, (lbl, line) in self.tabs.items():
            on = o == opt
            lbl.config(fg=P["accent"] if on else P["text_dim"])
            line.config(bg=P["accent"] if on else self.cget("bg"))
        if fire:
            self.command(opt)


class SearchEntry(tk.Frame):
    def __init__(self, master, command, placeholder="Search", width=24):
        super().__init__(master, bg=P["panel_hi"], highlightthickness=1, highlightbackground=P["edge"])
        self.command, self.placeholder = command, placeholder
        ic = tk.Canvas(self, width=24, height=24, bg=P["panel_hi"], highlightthickness=0)
        ic.create_oval(7, 6, 15, 14, outline=P["text_dim"], width=1.5)
        ic.create_line(14, 13, 18, 17, fill=P["text_dim"], width=1.5)
        ic.pack(side="left", padx=(3, 0))
        self.var = tk.StringVar(value=placeholder)
        self.entry = tk.Entry(self, textvariable=self.var, width=width, bd=0, relief="flat", bg=P["panel_hi"],
                              fg=P["text_faint"], insertbackground=P["accent"], font=FONTS["small"],
                              highlightthickness=0)
        self.entry.pack(side="left", padx=(2, 8), pady=4)
        self._ph = True
        self.entry.bind("<FocusIn>", self._in)
        self.entry.bind("<FocusOut>", self._out)
        self.entry.bind("<Escape>", lambda e: self.clear())
        self.var.trace_add("write", lambda *_: None if self._ph else self.command(self.var.get()))

    def _in(self, _e):
        self.config(highlightbackground=P["accent_dim"])
        if self._ph:
            self._ph = False
            self.var.set("")
            self.entry.config(fg=P["text"])

    def _out(self, _e):
        self.config(highlightbackground=P["edge"])
        if not self.var.get():
            self._ph = True
            self.entry.config(fg=P["text_faint"])
            self.var.set(self.placeholder)

    def clear(self):
        if not self._ph:
            self.var.set("")
        self.focus_set()


# ============================================================================
# Chart embedding (FigureCanvasTkAgg)
# ============================================================================
class ChartPanel(Panel):
    """Panel = title row + Matplotlib canvas + optional dimension legend underneath."""

    def __init__(self, master, plot, title=None, context=None, icon=None, legend=None, unit="",
                 min_w=240, min_h=150):
        super().__init__(master, title=title, context=context, icon=icon, pad=10)
        self.plot = plot
        self.canvas = FigureCanvasTkAgg(plot.figure, master=self.content)
        w = self.canvas.get_tk_widget()
        w.configure(bg=P["panel"], highlightthickness=0, bd=0, width=min_w, height=min_h)
        self.legend = None
        if legend:
            sep = tk.Frame(self.content, bg=P["edge"], height=1)
            self.legend = DimensionLegend(self.content, legend, unit, on_toggle=self._toggle)
            self.legend.pack(side="bottom", fill="x", pady=(8, 0))
            sep.pack(side="bottom", fill="x", pady=(6, 0))
        w.pack(fill="both", expand=True)

    def _toggle(self, hidden):
        if hasattr(self.plot, "set_hidden"):
            self.plot.set_hidden(hidden)
            if getattr(self, "_last_update", None):
                self._last_update()

    def redraw(self):
        self.canvas.draw_idle()


# ============================================================================
# Views
# ============================================================================
class BaseView(tk.Frame):
    title = ""
    crumb = ""

    def __init__(self, master, app):
        super().__init__(master, bg=P["bg"])
        self.app = app
        self._state = None

    def on_show(self):
        """Called when the view becomes visible."""

    def update_state(self, state):
        """Called with the latest ViewState while this view is visible."""

    def tick(self, now):
        """Called once per second (struct_time) while visible."""


# ============================================================================
# Overview view
# ============================================================================
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
        self.status = NumberCard(cards, "Monitoring status", icon="clock", big=False)
        for i, c in enumerate((self.cpu, self.ram, self.swap, self.load, self.status)):
            c.grid(row=0, column=i, sticky="nsew", padx=4, pady=4)

        # ---- per-core
        pc = Panel(main, title="Per-core utilization", context="cpu.cpuN", icon="cpu", pad=10)
        pc.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        legend_chips(pc.header_right, [("user", P["blue"]), ("system", P["red"]), ("other", P["amber"])])
        self.core_count = tk.Label(pc.header_right, text="— cores", font=FONTS["small_b"], fg=P["text"],
                                   bg=P["panel"], padx=8, highlightthickness=1, highlightbackground=P["edge"])
        self.core_count.pack(side="right", padx=(0, 14))
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
        self.update_status(s)
        self.core_count.config(text=f"{s.cores} CPU cores" if s.cores else "core count unavailable")
        self.cores.set(s.per_core)
        self._update_index(s)
        self._update_charts(s)

    def update_status(self, s=None):
        s = s or self._state
        app = self.app
        bits = []
        if s is not None:
            if s.interval_s:
                bits.append(f"every {s.interval_s:g}s")
            bits.append("updated " + time.strftime("%H:%M:%S", time.localtime(s.timestamp)))
            bits.append(f"{len(s.history.t)} samples")
        self.status.set(app.status_text, " · ".join(bits) or "waiting for data", color=app.status_color)

    def tick(self, now):
        self.update_status()      # reflect STALE / PAUSED even when no new data arrives

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


# ============================================================================
# Processes view
# ============================================================================
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
        self.table = ProcessTable(tb.content, colors=TABLE_COLORS, fonts=table_fonts())
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
            t.set_filter(lambda r: r.cpu is not None and r.cpu >= HIGH_CPU_MIN,
                         f"No processes above {HIGH_CPU_MIN:g}% CPU.", sort=("cpu", True))
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


# ============================================================================
# Analytics view
# ============================================================================
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
        self.chart = ChartPanel(self, self.grid_plot, "Utilization history", "dashed line = average",
                                "analytics", min_h=320)
        self.chart.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        side = tk.Frame(self, bg=P["bg"])
        side.grid(row=1, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        tp = Panel(side, title="Top resource consumers", icon="processes")
        tp.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.top_by = "cpu"
        TabControl(tp.header_right, ("CPU", "Memory"), self._on_top_tab).pack(side="right")
        self.top = BarList(tp.content, rows=8, empty_text="No processes available")
        self.top.pack(fill="x")
        al = Panel(side, title="Active alerts", icon="bell")
        al.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.alerts = AlertList(al.content, limit=7)
        self.alerts.pack(fill="both", expand=True)

    def _on_top_tab(self, name):
        self.top_by = "cpu" if name == "CPU" else "mem"
        if self._state is not None:
            self._update_top(self._state)

    def _update_top(self, s):
        """Top-N by %CPU or %MEM. Uses the analytics engine's lists when provided
        (top_processes / top_memory_processes), otherwise ranks the process list."""
        key = self.top_by
        ranked = s.top_memory_processes if key == "mem" else s.top_processes
        if not ranked:
            ranked = sorted((p for p in s.processes if getattr(p, key) is not None),
                            key=lambda p: getattr(p, key), reverse=True)
        self.top.set_items([(r.name, getattr(r, key)) for r in ranked[:8]])

    def update_state(self, s):
        self._state = s
        for key, tile in self.tiles.items():
            v = getattr(s, key)
            tile.set("—" if v is None else f"{v:.1f}", sub=f"over {len(s.history.t)} samples",
                     color=level_color(v) if v is not None and v >= 75 else None)
        self._update_top(s)
        self.alerts.set_alerts(s.alerts)
        self.grid_plot.update(s.history, s.timestamp, {"cpu": s.avg_cpu, "ram": s.avg_ram})
        self.chart.redraw()


# ============================================================================
# About view
# ============================================================================
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
        tk.Label(names, text=APP_NAME, font=FONTS["number_md"], fg=P["text"], bg=P["panel"]).pack(anchor="w")
        tk.Label(names, text=APP_TAGLINE, font=FONTS["body"], fg=P["text_dim"], bg=P["panel"]).pack(anchor="w")

        tk.Frame(c, bg=P["edge"], height=1).pack(fill="x", pady=20)

        def section(text, icon):
            row = tk.Frame(c, bg=P["panel"])
            row.pack(fill="x", pady=(0, 8))
            ic = tk.Canvas(row, width=16, height=16, bg=P["panel"], highlightthickness=0)
            draw_icon(ic, icon, 8, 8, P["accent"], s=6)
            ic.pack(side="left", padx=(0, 6))
            tk.Label(row, text=text, font=FONTS["small_b"], fg=P["accent"], bg=P["panel"]).pack(side="left")

        section("Team", "system")
        tk.Label(c, text=TEAM_NAME, font=FONTS["h1"], fg=P["text"], bg=P["panel"]).pack(anchor="w", pady=(0, 18))

        section("Members", "tasks")
        tbl = tk.Frame(c, bg=P["edge"])
        tbl.pack(fill="x", pady=(0, 18))
        tbl.columnconfigure(1, weight=1)
        for j, h in enumerate(("#", "Name", "Roll number")):
            tk.Label(tbl, text=h, font=FONTS["small_b"], fg=P["text"], bg=P["panel_hi"], anchor="w",
                     padx=10, pady=6).grid(row=0, column=j, sticky="ew", pady=(0, 1))
        for i, (name, roll) in enumerate(MEMBERS, start=1):
            bg = P["panel_lo"] if i % 2 else P["panel"]
            tk.Label(tbl, text=str(i), font=FONTS["mono_sm"], fg=P["text_faint"], bg=bg, padx=10, pady=6,
                     anchor="w").grid(row=i, column=0, sticky="ew")
            tk.Label(tbl, text=name, font=FONTS["body"], fg=P["text"], bg=bg, padx=10, anchor="w"
                     ).grid(row=i, column=1, sticky="nsew")
            tk.Label(tbl, text=roll, font=FONTS["mono_sm"], fg=P["text"], bg=bg, padx=10, anchor="w"
                     ).grid(row=i, column=2, sticky="nsew")

        section("Website", "host")
        LinkLabel(c, WEBSITE).pack(anchor="w")

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


# ============================================================================
# Main window
# ============================================================================
NAV = (
    ("overview", "Overview", OverviewView),
    ("processes", "Processes", ProcessesView),
    ("analytics", "Analytics", AnalyticsView),
    ("intro", "About", IntroView),
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


class Dashboard:
    def __init__(self, root, updates, on_close=None, source_name=""):
        """root: tk.Tk · updates: queue.Queue of ViewState / SourceError ·
        on_close: called before the window is destroyed (stop workers there) ·
        source_name: optional badge text, e.g. "DEMO DATA"."""
        self.root = root
        self.updates = updates
        self.on_close = on_close
        init_styles(root)
        root.title(APP_NAME)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(1440, sw - 40)}x{min(900, sh - 80)}")
        if sw <= 1600:                      # laptops (incl. 13"/14" MacBooks): start maximised
            maximize(root)
        root.minsize(1100, 700)
        self._set_icon()

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
        self.topbar = TopBar(main, self, source_name)
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
        setup_app(root, APP_NAME, self.shutdown)

        self.show("overview")
        self._schedule("poll", POLL_MS, self._poll)
        self._schedule("clock", 0, self._clock)

    def _set_icon(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.png")
        try:
            self._icon = tk.PhotoImage(file=path)
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass    # icon is cosmetic

    def _drain(self):
        """Newest item on the queue (older states are superseded), or None."""
        latest = None
        while True:
            try:
                latest = self.updates.get_nowait()
            except queue.Empty:
                return latest

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
        item = self._drain()
        if isinstance(item, SourceError):
            self.error = item.message
        elif isinstance(item, ViewState):
            self.last_rx, self.error = time.monotonic(), None
            self.latest = item
            if not self.paused:
                self._apply(item)
        self._update_status()
        self._schedule("poll", POLL_MS, self._poll)

    def _update_status(self):
        if self.error:
            text, col = "SOURCE ERROR", P["red"]
        elif self.paused:
            text, col = "PAUSED", P["amber"]
        elif self.last_rx is None:
            text, col = "CONNECTING", P["text_dim"]
        elif time.monotonic() - self.last_rx > STALE_AFTER_S:
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
        if self.on_close:
            try:
                self.on_close()
            except Exception as exc:      # never block closing the window
                print("on_close failed:", exc)
        self.root.quit()
        self.root.destroy()
