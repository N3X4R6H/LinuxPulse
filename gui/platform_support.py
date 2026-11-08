"""Small cross-platform helpers so the GUI behaves natively on Linux and macOS.

* Linux  : X11 or Wayland (via XWayland), any distro with Tk 8.6+.
* macOS  : Intel or Apple Silicon (M1–M5), python.org or Homebrew Python with Tk 8.6+/9.
"""
import sys
import tkinter as tk

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
