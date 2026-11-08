"""Reusable sortable, searchable, filterable process table (ttk.Treeview), top-style columns."""
import tkinter as tk
from tkinter import ttk

from .styles import P, FONTS

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
    def __init__(self, master):
        super().__init__(master, bg=P["panel"])
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(self, columns=[c[0] for c in COLUMNS], show="headings",
                                 style="Proc.Treeview", selectmode="browse")
        for key, label, width, anchor, stretch in COLUMNS:
            self.tree.heading(key, text=label, anchor=anchor, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, minwidth=50, anchor=anchor, stretch=stretch)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns", padx=(3, 0))

        self.tree.tag_configure("odd", background=P["panel_lo"])
        self.tree.tag_configure("even", background=P["panel"])
        self.tree.tag_configure("hot", foreground=P["red"])
        self.tree.tag_configure("warm", foreground=P["amber"])
        self.tree.tag_configure("run", foreground=P["accent"])
        self.tree.tag_configure("zombie", foreground=P["violet"])

        self.empty = tk.Label(self, font=FONTS["body"], fg=P["text_dim"], bg=P["panel"], justify="center")
        self.count_var = tk.StringVar(value="")
        self._rows = []
        self._sort_key, self._sort_desc = "cpu", True
        self._filter = None
        self._query = ""
        self._empty_msg = "No processes available."
        self._update_headings()

    def set_rows(self, rows):
        self._rows = list(rows)
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
            if q and q not in (r.name or "").lower() and q not in (r.user or "").lower() \
                    and not (r.pid is not None and str(r.pid).startswith(q)):
                continue
            out.append(r)
        k = self._sort_key
        present = [r for r in out if getattr(r, k) is not None]
        missing = [r for r in out if getattr(r, k) is None]
        keyf = (lambda r: getattr(r, k)) if k in NUMERIC else (lambda r: str(getattr(r, k)).lower())
        present.sort(key=keyf, reverse=self._sort_desc)
        return present + missing

    def _render(self):
        rows = self._visible()
        tree = self.tree
        existing = set(tree.get_children())
        seen = set()
        for idx, r in enumerate(rows):
            iid = f"p{r.pid}" if r.pid is not None else f"x{idx}"
            if iid in seen:
                iid = f"{iid}_{idx}"
            seen.add(iid)
            values = [_fmt(k, getattr(r, k)) for k, *_ in COLUMNS]
            tags = ["odd" if idx % 2 else "even"]
            if r.state == "Z":
                tags.append("zombie")
            elif r.cpu is not None and r.cpu >= 50:
                tags.append("hot")
            elif r.cpu is not None and r.cpu >= 20:
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
