"""Shared theme: palette, fonts and ttk styles (single source of truth)."""
from tkinter import ttk, font as tkfont

from .platform_support import font_scale

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


def init(root):
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
    _init_ttk(root)


def _init_ttk(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.layout("Proc.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("Proc.Treeview", background=P["panel"], fieldbackground=P["panel"],
                foreground=P["text"], rowheight=26, borderwidth=0, font=FONTS["mono_sm"])
    s.map("Proc.Treeview", background=[("selected", "#2c3d33")], foreground=[("selected", P["accent"])])
    s.configure("Proc.Treeview.Heading", background=P["panel_hi"], foreground=P["text"],
                relief="flat", borderwidth=0, font=FONTS["small_b"], padding=(6, 7))
    s.map("Proc.Treeview.Heading", background=[("active", P["edge"])], foreground=[("active", P["accent"])])
    s.configure("Dark.Vertical.TScrollbar", troughcolor=P["panel"], background=P["edge"],
                bordercolor=P["panel"], lightcolor=P["edge"], darkcolor=P["edge"],
                arrowcolor=P["text_faint"], gripcount=0, arrowsize=0, width=9)
    s.layout("Dark.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})], "sticky": "ns"})])
    s.map("Dark.Vertical.TScrollbar", background=[("active", P["edge_hi"]), ("pressed", P["accent_mid"])])
