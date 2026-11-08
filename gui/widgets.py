"""Reusable widgets in a flat, dense monitoring-tool style."""
import math
import time
import tkinter as tk
from tkinter import font as tkfont

from .styles import P, FONTS, blend, level_color


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
