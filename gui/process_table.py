"""ProcessTable — dedicated, self-contained component for displaying and sorting processes.

* Large lists: rows are diffed by PID (update / move / insert / delete) instead of rebuilt,
  so selection and scroll position survive every refresh.
* Empty lists: a centred message replaces the rows (configurable per filter).
* Sorting: click any heading (PID, USER, COMMAND, %CPU, %MEM, RES, TIME+, STATE);
  click again to reverse. Missing values (None) always sort last and display as "—".
* Search (PID prefix, user, command) and a filter predicate.

Rows are any objects with the attributes ``pid, user, name, cpu, mem, res_mib, time_s, state``
(e.g. ``gui.dashboard.ProcessRow``); missing attributes are treated as unavailable.
This module has no dependency on the rest of the GUI and can be used on its own.
"""
import tkinter as tk
from tkinter import ttk

COLUMNS = (
    # key, heading, width, anchor, stretch
    ("pid", "PID", 72, "e", False),
    ("user", "USER", 96, "w", False),
    ("name", "COMMAND", 260, "w", True),
    ("cpu", "%CPU", 76, "e", False),
    ("mem", "%MEM", 76, "e", False),
    ("res_mib", "RES", 84, "e", False),
    ("time_s", "TIME+", 92, "e", False),
    ("state", "STATE", 118, "w", False),
)
NUMERIC = {"pid", "cpu", "mem", "res_mib", "time_s"}
DESC_DEFAULT = {"cpu", "mem", "res_mib", "time_s"}
STATE_NAMES = {"R": "running", "S": "sleeping", "I": "idle", "D": "disk sleep",
               "Z": "zombie", "T": "stopped", "t": "traced"}

# Dark theme defaults; the dashboard passes its own palette/fonts in.
DEFAULT_COLORS = {
    "panel": "#23262a", "panel_hi": "#2b2e33", "panel_lo": "#1f2125", "edge": "#32353a",
    "edge_hi": "#4a4f56", "text": "#e8eaed", "text_dim": "#9aa0a6", "text_faint": "#6a7077",
    "accent": "#00d26a", "accent_mid": "#00ab44", "selected": "#2c3d33",
    "red": "#f0485b", "amber": "#f5a623", "violet": "#8f7cf7",
}
DEFAULT_FONTS = {"row": ("DejaVu Sans Mono", 9), "heading": ("DejaVu Sans", 9, "bold"),
                 "empty": ("DejaVu Sans", 10)}
HOT_CPU, WARM_CPU = 50.0, 20.0     # row highlight thresholds (%CPU)


def _get(row, key):
    return getattr(row, key, None)


def _fmt(key, v):
    if v is None:
        return "—"
    if key in ("cpu", "mem"):
        return f"{v:.1f}"
    if key == "res_mib":
        return f"{v / 1024:.2f}g" if v >= 1024 else f"{v:.1f}m"
    if key == "time_s":           # top TIME+ = minutes:seconds.hundredths
        m, s = divmod(v, 60)
        return f"{int(m)}:{s:05.2f}"
    if key == "state":
        return f"{v}  {STATE_NAMES.get(v, '')}".rstrip()
    return str(v)


class ProcessTable(tk.Frame):
    def __init__(self, master, colors=None, fonts=None):
        self.c = dict(DEFAULT_COLORS, **(colors or {}))
        self.f = dict(DEFAULT_FONTS, **(fonts or {}))
        super().__init__(master, bg=self.c["panel"])
        self._init_style()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(self, columns=[col[0] for col in COLUMNS], show="headings",
                                 style="Proc.Treeview", selectmode="browse")
        for key, label, width, anchor, stretch in COLUMNS:
            self.tree.heading(key, text=label, anchor=anchor, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, minwidth=50, anchor=anchor, stretch=stretch)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview, style="Proc.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns", padx=(3, 0))

        c = self.c
        self.tree.tag_configure("odd", background=c["panel_lo"])
        self.tree.tag_configure("even", background=c["panel"])
        self.tree.tag_configure("hot", foreground=c["red"])
        self.tree.tag_configure("warm", foreground=c["amber"])
        self.tree.tag_configure("zombie", foreground=c["violet"])

        self.empty = tk.Label(self, font=self.f["empty"], fg=c["text_dim"], bg=c["panel"], justify="center")
        self.count_var = tk.StringVar(value="")
        self._rows = []
        self._sort_key, self._sort_desc = "cpu", True
        self._filter = None
        self._query = ""
        self._empty_msg = "No processes available."
        self._update_headings()

    def _init_style(self):
        c, s = self.c, ttk.Style(self)
        if s.theme_use() not in ("clam", "alt", "default"):
            s.theme_use("clam")           # native themes ignore custom colours
        s.layout("Proc.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure("Proc.Treeview", background=c["panel"], fieldbackground=c["panel"],
                    foreground=c["text"], rowheight=26, borderwidth=0, font=self.f["row"])
        s.map("Proc.Treeview", background=[("selected", c["selected"])], foreground=[("selected", c["accent"])])
        s.configure("Proc.Treeview.Heading", background=c["panel_hi"], foreground=c["text"],
                    relief="flat", borderwidth=0, font=self.f["heading"], padding=(6, 7))
        s.map("Proc.Treeview.Heading", background=[("active", c["edge"])], foreground=[("active", c["accent"])])
        s.layout("Proc.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})], "sticky": "ns"})])
        s.configure("Proc.Vertical.TScrollbar", troughcolor=c["panel"], background=c["edge"],
                    bordercolor=c["panel"], lightcolor=c["edge"], darkcolor=c["edge"], gripcount=0, width=9)
        s.map("Proc.Vertical.TScrollbar", background=[("active", c["edge_hi"]), ("pressed", c["accent_mid"])])

    # ---------------------------------------------------------------- public API
    def set_rows(self, rows):
        self._rows = list(rows or [])
        self._render()

    def set_query(self, text):
        self._query = (text or "").strip().lower()
        self._render()

    def set_filter(self, predicate, empty_message="No processes match this filter.", sort=None):
        self._filter, self._empty_msg = predicate, empty_message
        if sort:
            self._sort_key, self._sort_desc = sort
            self._update_headings()
        self._render()

    def sort_by(self, key):
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key, self._sort_desc = key, key in DESC_DEFAULT
        self._update_headings()
        self._render()

    # ---------------------------------------------------------------- internals
    def _update_headings(self):
        for key, label, *_ in COLUMNS:
            arrow = (" ↓" if self._sort_desc else " ↑") if key == self._sort_key else ""
            self.tree.heading(key, text=label + arrow)

    def _visible(self):
        q = self._query
        out = []
        for r in self._rows:
            if self._filter and not self._filter(r):
                continue
            if q:
                pid = _get(r, "pid")
                if q not in str(_get(r, "name") or "").lower() and q not in str(_get(r, "user") or "").lower() \
                        and not (pid is not None and str(pid).startswith(q)):
                    continue
            out.append(r)
        k = self._sort_key
        present = [r for r in out if _get(r, k) is not None]
        missing = [r for r in out if _get(r, k) is None]
        if k in NUMERIC:
            def keyf(r):
                try:
                    return float(_get(r, k))
                except (TypeError, ValueError):
                    return float("-inf")
        else:
            def keyf(r):
                return str(_get(r, k)).lower()
        present.sort(key=keyf, reverse=self._sort_desc)
        return present + missing

    def _render(self):
        rows = self._visible()
        tree = self.tree
        existing = set(tree.get_children())
        seen = set()
        for idx, r in enumerate(rows):
            pid = _get(r, "pid")
            iid = f"p{pid}" if pid is not None else f"x{idx}"
            if iid in seen:
                iid = f"{iid}_{idx}"
            seen.add(iid)
            values = [_fmt(k, _get(r, k)) for k, *_ in COLUMNS]
            tags = ["odd" if idx % 2 else "even"]
            cpu = _get(r, "cpu")
            if _get(r, "state") == "Z":
                tags.append("zombie")
            elif cpu is not None and cpu >= HOT_CPU:
                tags.append("hot")
            elif cpu is not None and cpu >= WARM_CPU:
                tags.append("warm")
            if iid in existing:
                tree.item(iid, values=values, tags=tags)
                tree.move(iid, "", idx)
            else:
                tree.insert("", idx, iid=iid, values=values, tags=tags)
        stale = existing - seen
        if stale:
            tree.delete(*stale)
        self.count_var.set(f"{len(rows)} of {len(self._rows)}")
        if rows:
            self.empty.place_forget()
        else:
            msg = self._empty_msg if (self._rows or self._filter) else "No processes available."
            if self._query and self._rows:
                msg = f"No processes match “{self._query}”."
            self.empty.config(text=msg)
            self.empty.place(relx=0.5, rely=0.5, anchor="center")
