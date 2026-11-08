"""INTERIM visualization layer used by the GUI — visualization/ is Pavan's module.

Kept here only so the dashboard runs on its own. Pavan may adopt or replace it; the GUI
needs objects that expose ``.figure`` (a matplotlib Figure) and ``.update(...)`` with the
signatures below (also listed in docs/gui_design.md, "Interfaces the GUI expects").

Matplotlib figure objects for the dashboard (no Tkinter here).

Each class owns a ``matplotlib.figure.Figure`` and exposes ``update(...)``.
X axes are wall-clock times (epoch seconds formatted as HH:MM:SS).
"""
import math
import time

from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

THEME = {
    "face": "#23262a", "fg": "#7d838a", "text": "#e8eaed", "text_dim": "#9aa0a6",
    "grid": "#2f3237", "muted": "#383c42", "accent": "#00d26a",
}
NAN = float("nan")
HEAT_CMAP = LinearSegmentedColormap.from_list(
    "core_heat", ["#1f2a25", "#0b6b3a", "#00c060", "#f2c94c", "#f0485b"])
HEAT_CMAP.set_bad(THEME["face"])


def _blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _clock(v, _p):
    return time.strftime("%H:%M:%S", time.localtime(v)) if v > 0 else ""


def style_axes(ax, th=THEME, ylabel=None):
    ax.set_facecolor(th["face"])
    for k, sp in ax.spines.items():
        sp.set_visible(k == "bottom")
        sp.set_color(th["muted"])
    ax.tick_params(colors=th["fg"], labelsize=7.5, length=0, pad=5)
    ax.grid(True, color=th["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(FuncFormatter(_clock))
    ax.xaxis.set_major_locator(MaxNLocator(5))
    if ylabel:
        ax.set_ylabel(ylabel, color=th["fg"], fontsize=7.5, labelpad=6)


def _vals(ys):
    return [NAN if v is None else float(v) for v in ys]


def _window(ax, times, window):
    """Fill the axes with the available history (at most ``window`` seconds)."""
    end = times[-1] if times else time.time()
    start = max(times[0], end - window) if len(times) > 1 else end - window
    ax.set_xlim(start, end)


class StackedAreaPlot:
    """Stacked dimensions, e.g. CPU user/system/iowait/... or memory used/cache/free."""

    def __init__(self, dims, window=300, ylim=(0, 100), ylabel="percentage", yfmt="{:.0f}"):
        self.dims, self.window, self.ylim = dims, window, ylim
        self.hidden = set()
        self.figure = Figure(figsize=(6, 2.6), dpi=100, facecolor=THEME["face"], layout="constrained")
        self.ax = ax = self.figure.add_subplot(111)
        style_axes(ax, ylabel=ylabel)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: yfmt.format(v)))
        if ylim:
            ax.set_ylim(*ylim)
        self.lines = {k: ax.plot([], [], color=_blend(c, "#ffffff", .25), lw=1.0)[0] for k, _l, c in dims}
        self.fills = []
        self.empty = ax.text(0.5, 0.5, "Waiting for data…", transform=ax.transAxes, ha="center",
                             va="center", color=THEME["fg"], fontsize=9)

    def set_hidden(self, hidden):
        self.hidden = set(hidden)

    def update(self, times, series, ymax=None):
        ax = self.ax
        for f in self.fills:
            f.remove()
        self.fills = []
        n = len(times)
        base = [0.0] * n
        any_data = False
        for key, _label, color in self.dims:
            line = self.lines[key]
            if key in self.hidden or key not in series or not n:
                line.set_data([], [])
                continue
            vals = _vals(series[key])
            top = [b + v for b, v in zip(base, vals)]
            any_data = any_data or any(not math.isnan(v) for v in vals)
            self.fills.append(ax.fill_between(times, base, top, color=color, alpha=0.88, lw=0))
            line.set_data(times, top)
            base = [b if math.isnan(t) else t for b, t in zip(base, top)]
        self.empty.set_visible(not any_data)
        self.empty.set_text("Unavailable" if n else "Waiting for data…")
        _window(ax, times, self.window)
        if ymax is not None:
            ax.set_ylim(0, ymax)


class MemoryPie:
    """Donut of used vs available memory."""

    def __init__(self, used_color="#00d26a"):
        self.used_color = used_color
        self.figure = Figure(figsize=(3.2, 3.2), dpi=100, facecolor=THEME["face"], layout="constrained")
        self.ax = self.figure.add_subplot(111)
        self._last = object()
        self.update(None, None)

    def update(self, used, available, unit="GiB"):
        key = None if used is None or available is None else (round(used, 2), round(available, 2))
        if key == self._last:
            return
        self._last = key
        ax = self.ax
        ax.clear()
        ax.set_aspect("equal")
        ax.axis("off")
        wp = dict(width=0.2, edgecolor=THEME["face"], linewidth=2)
        if key is None:
            ax.pie([1], colors=[THEME["muted"]], wedgeprops=wp)
            ax.text(0, 0.05, "—", ha="center", va="center", color=THEME["fg"], fontsize=22, fontweight="bold")
            ax.text(0, -0.22, "memory unavailable", ha="center", color=THEME["fg"], fontsize=8)
            return
        total = used + available
        pct = 100 * used / total if total else 0.0
        ax.pie([used, available], colors=[self.used_color, THEME["muted"]], startangle=90,
               counterclock=False, wedgeprops=wp)
        ax.text(0, 0.08, f"{pct:.1f}", ha="center", va="center", color=THEME["text"],
                fontsize=24, fontweight="bold")
        ax.text(0, -0.2, "% used", ha="center", va="center", color=THEME["text_dim"], fontsize=8.5)
        ax.text(-0.04, -1.3, f"■ used {used:.2f} {unit}", ha="right", va="center", color=self.used_color, fontsize=8.5)
        ax.text(0.08, -1.3, f"■ available {available:.2f} {unit}", ha="left", va="center",
                color=THEME["text_dim"], fontsize=8.5)
        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-1.45, 1.15)


class _Line:
    def __init__(self, ax, color):
        self.ax, self.color = ax, color
        self.line, = ax.plot([], [], color=color, lw=1.4)
        self.fill = None

    def set(self, times, vals):
        if self.fill:
            self.fill.remove()
            self.fill = None
        self.line.set_data(times, vals)
        if times:
            self.fill = self.ax.fill_between(times, vals, 0, color=self.color, alpha=0.22, lw=0)
        return [v for v in vals if not math.isnan(v)]


class AnalyticsGrid:
    """CPU / RAM / SWAP / load histories plus a per-core utilisation heatmap."""

    SPECS = (("cpu", "CPU utilization", True), ("ram", "RAM utilization", True),
             ("swap", "SWAP utilization", True), ("load1", "System load (1 min)", False))

    def __init__(self, colors, window=300):
        self.window = window
        self.figure = Figure(figsize=(8, 6.4), dpi=100, facecolor=THEME["face"], layout="constrained")
        self.figure.get_layout_engine().set(w_pad=0.1, h_pad=0.1, hspace=0.07, wspace=0.05)
        gs = self.figure.add_gridspec(3, 2, height_ratios=[1, 1, 1.1])
        self.panels = {}
        for (key, title, pct), cell in zip(self.SPECS, (gs[0, 0], gs[0, 1], gs[1, 0], gs[1, 1])):
            ax = self.figure.add_subplot(cell)
            style_axes(ax)
            if pct:
                ax.set_ylim(0, 100)
                ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
            ax.text(0, 1.03, title, transform=ax.transAxes, color=THEME["text"], fontsize=8, va="bottom")
            readout = ax.text(1, 1.03, "", transform=ax.transAxes, color=colors[key], fontsize=8.5,
                              fontweight="bold", va="bottom", ha="right")
            avg = ax.axhline(NAN, color=THEME["text_dim"], lw=0.8, ls=(0, (4, 3)))
            empty = ax.text(0.5, 0.5, "Waiting for data…", transform=ax.transAxes, ha="center",
                            va="center", color=THEME["fg"], fontsize=8)
            self.panels[key] = dict(ax=ax, s=_Line(ax, colors[key]), pct=pct, readout=readout,
                                    avg=avg, empty=empty)
        self.hax = self.figure.add_subplot(gs[2, :])
        style_axes(self.hax)
        self.hax.grid(False)
        self.hax.text(0, 1.03, "Per-core utilization", transform=self.hax.transAxes, color=THEME["text"],
                      fontsize=8, va="bottom")
        self.heat = None
        self.heat_cores = None
        self.heat_empty = self.hax.text(0.5, 0.5, "Per-CPU data unavailable", transform=self.hax.transAxes,
                                        ha="center", va="center", color=THEME["fg"], fontsize=8)

    def update(self, history, now, averages=None):
        averages = averages or {}
        times = [now + t for t in history.t]
        for key, p in self.panels.items():
            vals = _vals(getattr(history, key))
            valid = p["s"].set(times, vals)
            p["empty"].set_visible(not valid)
            p["empty"].set_text("Unavailable" if times else "Waiting for data…")
            ax = p["ax"]
            _window(ax, times, self.window)
            if valid:
                p["readout"].set_text(f"{valid[-1]:.1f}%" if p["pct"] else f"{valid[-1]:.2f}")
                if not p["pct"]:
                    ax.set_ylim(0, max(1.0, max(valid) * 1.3))
            else:
                p["readout"].set_text("—")
            a = averages.get(key)
            p["avg"].set_ydata([NAN, NAN] if a is None else [a, a])
        self._update_heat(times, history.per_core)

    def _update_heat(self, times, per_core):
        rows = [s for s in per_core if s]
        if not times or not rows:
            self.heat_empty.set_visible(True)
            return
        self.heat_empty.set_visible(False)
        n = max(len(s) for s in rows)
        matrix = [[NAN] * len(times) for _ in range(n)]
        for j, sample in enumerate(per_core):
            for c, v in enumerate(sample or []):
                if v is not None:
                    matrix[c][j] = v
        dt = (times[-1] - times[0]) / max(1, len(times) - 1) if len(times) > 1 else 1.0
        extent = (times[0] - dt / 2, times[-1] + dt / 2, -0.5, n - 0.5)
        if self.heat is None or self.heat_cores != n:
            if self.heat is not None:
                self.heat.remove()
            self.heat = self.hax.imshow(matrix, aspect="auto", origin="lower", interpolation="nearest",
                                        cmap=HEAT_CMAP, vmin=0, vmax=100, extent=extent)
            if self.heat_cores is None:
                cb = self.figure.colorbar(self.heat, ax=self.hax, fraction=0.02, pad=0.01)
                cb.outline.set_visible(False)
                cb.ax.tick_params(colors=THEME["fg"], labelsize=7, length=0)
                cb.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}%"))
            self.heat_cores = n
            step = max(1, math.ceil(n / 8))
            self.hax.set_yticks(range(0, n, step))
            self.hax.set_yticklabels([f"cpu{i}" for i in range(0, n, step)])
        else:
            self.heat.set_data(matrix)
            self.heat.set_extent(extent)
        _window(self.hax, times, self.window)
