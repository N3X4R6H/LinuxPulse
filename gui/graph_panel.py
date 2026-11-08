"""Embeds a visualization object's Matplotlib figure inside a Panel."""
import tkinter as tk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from .styles import P
from .widgets import DimensionLegend, Panel


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
