"""Gemeinsames Look & Feel: dunkles Graphit, ein warmer Bernstein-Akzent."""

from tkinter import ttk

BG = "#17181a"
SURFACE = "#202225"
SURFACE_HI = "#2a2d31"
LINE = "#33363b"
TEXT = "#e8e6e1"
MUTED = "#8b8f96"
ACCENT = "#f2a541"
ACCENT_DIM = "#b97a2b"
DANGER = "#e5604d"

FONT = "Segoe UI Variable Text"
FONT_DISPLAY = "Segoe UI Variable Display"
MONO = "Cascadia Mono"


def apply(root) -> ttk.Style:
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10), bordercolor=LINE,
                    focuscolor=ACCENT, lightcolor=SURFACE, darkcolor=SURFACE, troughcolor=SURFACE)
    style.configure("TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Sidebar.TFrame", background=SURFACE)

    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=(FONT_DISPLAY, 20, "bold"))
    style.configure("Section.TLabel", foreground=MUTED, font=(FONT, 8, "bold"))
    style.configure("Brand.TLabel", background=SURFACE, foreground=ACCENT, font=(MONO, 13, "bold"))
    style.configure("SidebarMuted.TLabel", background=SURFACE, foreground=MUTED, font=(FONT, 8, "bold"))
    style.configure("Big.TLabel", font=(MONO, 44, "bold"))
    style.configure("Status.TLabel", font=(MONO, 9, "bold"), foreground=MUTED)
    style.configure("StatusOn.TLabel", font=(MONO, 9, "bold"), foreground=ACCENT)

    # Sidebar-Einträge
    style.configure("Nav.TButton", background=SURFACE, foreground=MUTED, borderwidth=0,
                    anchor="w", padding=(18, 9), font=(FONT, 10))
    style.map("Nav.TButton", background=[("active", SURFACE_HI)], foreground=[("active", TEXT)])
    style.configure("NavActive.TButton", background=SURFACE_HI, foreground=TEXT, borderwidth=0,
                    anchor="w", padding=(18, 9), font=(FONT, 10, "bold"))
    style.map("NavActive.TButton", background=[("active", SURFACE_HI)])

    style.configure("TButton", background=SURFACE_HI, foreground=TEXT, borderwidth=1,
                    padding=(12, 6), relief="flat")
    style.map("TButton", background=[("active", LINE), ("disabled", SURFACE)],
              foreground=[("disabled", MUTED)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#1a1306", borderwidth=0,
                    padding=(18, 10), font=(FONT, 11, "bold"))
    style.map("Accent.TButton", background=[("active", "#f7b860")])
    style.configure("Stop.TButton", background=DANGER, foreground="#1a0805", borderwidth=0,
                    padding=(18, 10), font=(FONT, 11, "bold"))
    style.map("Stop.TButton", background=[("active", "#ee7a69")])

    for widget in ("TRadiobutton", "TCheckbutton"):
        style.configure(widget, background=BG, foreground=TEXT, indicatorbackground=SURFACE_HI,
                        indicatorforeground=ACCENT, upperbordercolor=LINE, lowerbordercolor=LINE)
        style.map(widget, background=[("active", BG)],
                  indicatorbackground=[("pressed", ACCENT_DIM)])

    style.configure("Seg.TRadiobutton", background=SURFACE, foreground=MUTED, padding=(14, 6),
                    indicatorsize=0, indicatorrelief="flat", borderwidth=0)
    style.layout("Seg.TRadiobutton", [("Radiobutton.padding", {"sticky": "nswe", "children": [
        ("Radiobutton.label", {"sticky": "nswe"})]})])
    style.map("Seg.TRadiobutton", background=[("selected", ACCENT), ("active", SURFACE_HI)],
              foreground=[("selected", "#1a1306"), ("active", TEXT)])

    style.configure("TSpinbox", fieldbackground=SURFACE, foreground=TEXT, arrowcolor=MUTED,
                    background=SURFACE_HI, insertcolor=TEXT, padding=(6, 4), font=(MONO, 10))
    style.map("TSpinbox", fieldbackground=[("focus", SURFACE_HI)], bordercolor=[("focus", ACCENT)])
    style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT, insertcolor=TEXT,
                    padding=(6, 4), font=(MONO, 10))
    style.map("TEntry", fieldbackground=[("focus", SURFACE_HI)], bordercolor=[("focus", ACCENT)])
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    borderwidth=0, rowheight=24, font=(FONT, 9))
    style.map("Treeview", background=[("selected", SURFACE_HI)], foreground=[("selected", ACCENT)])
    style.configure("TSeparator", background=LINE)
    return style
