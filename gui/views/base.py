import tkinter as tk

from ..styles import P


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
