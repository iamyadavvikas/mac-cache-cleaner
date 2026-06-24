#!/usr/bin/env python3
"""CleanMyMac X-like macOS cleaner – polished GUI."""

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from dataclasses import dataclass, field
from functools import partial

HOME = Path.home()

# ── Colors ────────────────────────────────────────────────────────────────

C_BG = "#F5F6FA"
C_SIDEBAR = "#2C2E3E"
C_SIDEBAR_SEL = "#3A3D51"
C_SIDEBAR_TEXT = "#A0A3B4"
C_SIDEBAR_TEXT_SEL = "#FFFFFF"
C_ACCENT = "#4A7CFE"
C_ACCENT_HOVER = "#3A66DB"
C_GREEN = "#34C759"
C_RED = "#FF3B30"
C_ORANGE = "#FF9500"
C_CARD_BG = "#FFFFFF"
C_TEXT = "#1C1C1E"
C_TEXT_SEC = "#8E8E93"
C_BORDER = "#E5E5EA"
C_PROGRESS_BG = "#E5E5EA"
C_CHECK_ON = "#4A7CFE"
C_CHECK_OFF = "#C7C7CC"

CAT_COLORS = ["#4A7CFE", "#FF9500", "#34C759", "#FF3B30", "#AF52DE", "#FF6482"]
CAT_ICONS = ["☕", "📝", "🗑", "💻", "🔄", "📥"]

FONT = ("-apple-system", "SF Pro Text", "Helvetica Neue", 13)
FONT_BOLD = ("-apple-system", "SF Pro Text", "Helvetica Neue", 13, "bold")
FONT_SM = ("-apple-system", "SF Pro Text", "Helvetica Neue", 12)
FONT_XS = ("-apple-system", "SF Pro Text", "Helvetica Neue", 11)
FONT_TITLE = ("-apple-system", "SF Pro Display", "Helvetica Neue", 24, "bold")
FONT_SUB = ("-apple-system", "SF Pro Display", "Helvetica Neue", 16, "bold")
FONT_MONO = ("Menlo", 11)
FONT_BIG = ("-apple-system", "SF Pro Display", "Helvetica Neue", 36, "bold")


# ── Data ──────────────────────────────────────────────────────────────────

@dataclass
class Category:
    name: str
    paths: list[Path] = field(default_factory=list)
    items: list[tuple[Path, int, str]] = field(default_factory=list)
    scanned_size: int = 0
    scanned_count: int = 0


CATEGORIES: list[Category] = [
    Category("System Caches", [
        HOME / "Library" / "Caches",
        HOME / ".cache",
        HOME / ".npm" / "_cacache",
        HOME / ".yarn" / "cache",
        HOME / ".pnpm-store",
        HOME / ".gradle" / "caches",
        HOME / ".m2" / "repository",
        HOME / ".bundle" / "cache",
        HOME / ".composer" / "cache",
        HOME / ".cargo" / "registry",
        HOME / "go" / "pkg" / "mod",
        HOME / "Library" / "Application Support" / "*" / "Cache",
        HOME / "Library" / "Application Support" / "*" / "cache",
        HOME / "Library" / "Application Support" / "*" / "Caches",
        HOME / "Library" / "Application Support" / "*" / "caches",
    ]),
    Category("User Logs", [
        HOME / "Library" / "Logs",
        HOME / "Library" / "Application Support" / "*" / "Logs",
        HOME / "Library" / "Application Support" / "*" / "logs",
    ]),
    Category("Trash", [
        HOME / ".Trash",
    ]),
    Category("Xcode Junk", [
        HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
        HOME / "Library" / "Developer" / "Xcode" / "Archives",
        HOME / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport",
        HOME / "Library" / "Developer" / "CoreSimulator" / "Caches",
        HOME / "Library" / "Application Support" / "Simulator",
    ]),
    Category("Temp Files", [
        Path("/tmp"),
        Path("/var/tmp"),
    ]),
    Category("Downloads", [
        HOME / "Downloads",
    ]),
]


def human_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def dir_size(path: Path) -> int:
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    pass
    except (PermissionError, OSError):
        pass
    return total


def delete_item(path: Path) -> bool:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
        else:
            shutil.rmtree(path, onerror=lambda fn, p, e: None)
        return True
    except PermissionError:
        try:
            subprocess.run(["sudo", "rm", "-rf", str(path)], capture_output=True, timeout=30)
            return not path.exists()
        except Exception:
            return False
    except Exception:
        return False


def scan_category(cat: Category) -> None:
    cat.items.clear()
    seen = set()
    for pattern in cat.paths:
        if "*" in str(pattern):
            parent = pattern.parent
            for p in parent.glob(pattern.name):
                if p.exists() and str(p) not in seen:
                    seen.add(str(p))
                    sz = dir_size(p)
                    if sz:
                        cat.items.append((p, sz, human_size(sz)))
        else:
            if pattern.exists() and str(pattern) not in seen:
                seen.add(str(pattern))
                sz = dir_size(pattern)
                if sz:
                    cat.items.append((pattern, sz, human_size(sz)))
    cat.items.sort(key=lambda x: x[1], reverse=True)
    cat.scanned_size = sum(sz for _, sz, _ in cat.items)
    cat.scanned_count = len(cat.items)


# ── Checkbox widget ──────────────────────────────────────────────────────

class Checkbox(tk.Canvas):
    def __init__(self, master, checked=False, command=None, **kw):
        size = kw.pop("size", 18)
        super().__init__(master, width=size + 4, height=size + 4,
                         highlightthickness=0, bg=master.cget("bg") or C_BG, **kw)
        self.size = size
        self._checked = checked
        self._command = command
        self._bind()
        self.draw()

    def _bind(self):
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", lambda e: self.config(cursor="hand2"))
        self.bind("<Leave>", lambda e: self.config(cursor=""))

    def draw(self):
        self.delete("all")
        s = self.size
        x, y = 2, 2
        r = 4
        if self._checked:
            self.create_rectangle(x, y, x + s, y + s, fill=C_CHECK_ON,
                                  outline=C_CHECK_ON, radius=r)
            self.create_line(x + 4, y + s // 2, x + s // 2 - 1, y + s - 4,
                             fill="white", width=2.5, capstyle=tk.ROUND)
            self.create_line(x + s // 2 - 1, y + s - 4, x + s - 4, y + 4,
                             fill="white", width=2.5, capstyle=tk.ROUND)
        else:
            self.create_rectangle(x, y, x + s, y + s, fill=C_CARD_BG,
                                  outline=C_CHECK_OFF, width=1.5, radius=r)

    def _toggle(self, event=None):
        self._checked = not self._checked
        self.draw()
        if self._command:
            self._command(self._checked)

    def get(self):
        return self._checked

    def set(self, val):
        self._checked = val
        self.draw()


# ── Rounded rect canvas ──────────────────────────────────────────────────

def _create_rect(self, x1, y1, x2, y2, **kw):
    r = kw.pop("radius", 8)
    points = [x1 + r, y1,
              x1 + r, y1,
              x2 - r, y1,
              x2 - r, y1,
              x2, y1,
              x2, y1 + r,
              x2, y1 + r,
              x2, y2 - r,
              x2, y2 - r,
              x2, y2,
              x2 - r, y2,
              x2 - r, y2,
              x1 + r, y2,
              x1 + r, y2,
              x1, y2,
              x1, y2 - r,
              x1, y2 - r,
              x1, y1 + r,
              x1, y1 + r,
              x1, y1]
    return self.create_polygon(points, **kw, smooth=True, splinesteps=12)

tk.Canvas.create_round_rect = _create_rect


# ── Main App ─────────────────────────────────────────────────────────────

class CleanMyMacApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Cache Cleaner")
        self.root.geometry("1050x680")
        self.root.minsize(850, 520)
        self.root.configure(bg=C_BG)

        self._freed_bytes = 0
        self.selected_category: int | None = None
        self.checked_vars: dict[str, tk.BooleanVar] = {}
        self.scanning = False

        self._build_layout()
        self._bind_shortcuts()

    def _bind_shortcuts(self):
        self.root.bind("<Command-w>", lambda e: self.root.destroy())
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    # ── Layout ────────────────────────────────────────────────────────────

    def _build_layout(self):
        # dark title bar
        title_bar = tk.Frame(self.root, bg=C_SIDEBAR, height=44)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="✦  Cache Cleaner", font=FONT_BOLD,
                 fg="white", bg=C_SIDEBAR).pack(side=tk.LEFT, padx=16, pady=10)

        self.freed_badge = tk.Label(title_bar, text="", font=FONT_SM,
                                    fg=C_GREEN, bg=C_SIDEBAR)
        self.freed_badge.pack(side=tk.RIGHT, padx=16)

        # body
        body = tk.Frame(self.root, bg=C_BG)
        body.pack(fill=tk.BOTH, expand=True)

        # ── sidebar ──
        self.sidebar = tk.Frame(body, bg=C_SIDEBAR, width=220)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.side_btns: list[tk.Frame] = []
        for i, cat in enumerate(CATEGORIES):
            btn = self._make_side_btn(i, cat)
            btn.pack(fill=tk.X, padx=8, pady=2)
            self.side_btns.append(btn)

        # spacer
        tk.Frame(self.sidebar, bg=C_SIDEBAR).pack(fill=tk.BOTH, expand=True)

        # ── content ──
        content_bg = tk.Frame(body, bg=C_BG)
        content_bg.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.content = tk.Frame(content_bg, bg=C_BG)
        self.content.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # header
        self.cat_color = C_ACCENT
        self.header = tk.Frame(self.content, bg=C_BG)
        self.header.pack(fill=tk.X, pady=(0, 4))

        self.cat_icon_lbl = tk.Label(self.header, text="", font=("Helvetica Neue", 28),
                                     bg=C_BG)
        self.cat_icon_lbl.pack(side=tk.LEFT, padx=(0, 10))

        hdr_right = tk.Frame(self.header, bg=C_BG)
        hdr_right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cat_title = tk.Label(hdr_right, text="Select a category", font=FONT_SUB,
                                  fg=C_TEXT, bg=C_BG, anchor=tk.W)
        self.cat_title.pack(fill=tk.X)
        self.cat_stats = tk.Label(hdr_right, text="Click Scan to analyze your system",
                                  font=FONT_XS, fg=C_TEXT_SEC, bg=C_BG, anchor=tk.W)
        self.cat_stats.pack(fill=tk.X)

        # progress
        self.progress_frame = tk.Frame(self.content, bg=C_BG)
        self.progress_frame.pack(fill=tk.X, pady=(0, 0))
        self.progress = ttk.Progressbar(self.progress_frame, mode="determinate",
                                        length=400, style="Clean.Horizontal.TProgressbar")
        self.progress_label = tk.Label(self.progress_frame, text="", font=FONT_XS,
                                       fg=C_TEXT_SEC, bg=C_BG)
        self.scan_progress_label = self.progress_label

        # selected size badge
        stats_row = tk.Frame(self.content, bg=C_BG)
        stats_row.pack(fill=tk.X, pady=(6, 10))
        self.selected_lbl = tk.Label(stats_row, text="", font=FONT_BOLD,
                                     fg=C_ACCENT, bg=C_BG)
        self.selected_lbl.pack(side=tk.LEFT)
        self.item_count_lbl = tk.Label(stats_row, text="", font=FONT_XS,
                                       fg=C_TEXT_SEC, bg=C_BG)
        self.item_count_lbl.pack(side=tk.LEFT, padx=(8, 0))

        # scrollable item list
        list_container = tk.Frame(self.content, bg=C_BG)
        list_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(list_container, bg=C_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable = tk.Frame(self.canvas, bg=C_BG)

        self.scrollable.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable, anchor="nw", tags="inner")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # mousewheel scroll
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        # ── bottom bar ──
        bot = tk.Frame(self.root, bg=C_CARD_BG, height=56)
        bot.pack(fill=tk.X)
        bot.pack_propagate(False)

        bot_inner = tk.Frame(bot, bg=C_CARD_BG)
        bot_inner.pack(fill=tk.X, padx=20, pady=8)

        self.status = tk.Label(bot_inner, text="✓ Ready", font=FONT_SM,
                               fg=C_TEXT_SEC, bg=C_CARD_BG)
        self.status.pack(side=tk.LEFT)

        self.scan_btn = self._accent_btn(bot_inner, "⏣  Scan", self.start_scan)
        self.scan_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.select_btn = self._outline_btn(bot_inner, "Select All", self.select_all)
        self.select_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.select_btn.config(state=tk.DISABLED)

        self.clean_btn = self._accent_btn(bot_inner, "✕  Clean Selected", self.clean_selected,
                                          bg=C_RED)
        self.clean_btn.pack(side=tk.RIGHT)
        self.clean_btn.config(state=tk.DISABLED)

        # style override for ttk progress
        style = ttk.Style()
        style.theme_use("aqua" if "aqua" in style.theme_names() else "default")
        style.configure("Clean.Horizontal.TProgressbar", thickness=6, troughcolor=C_PROGRESS_BG,
                        background=C_ACCENT, lightcolor=C_ACCENT, darkcolor=C_ACCENT)

        self.progress_frame.pack_forget()  # hidden until scan

    # ── Sidebar buttons ──────────────────────────────────────────────────

    def _make_side_btn(self, idx: int, cat: Category) -> tk.Frame:
        frame = tk.Frame(self.sidebar, bg=C_SIDEBAR, cursor="hand2")
        # accent bar
        self._bar = tk.Frame(frame, bg=C_SIDEBAR, width=3)
        self._bar.pack(side=tk.LEFT, fill=tk.Y)
        self._bar.pack_propagate(False)

        icon_lbl = tk.Label(frame, text=CAT_ICONS[idx], font=("Helvetica Neue", 16),
                            bg=C_SIDEBAR, fg=C_SIDEBAR_TEXT)
        icon_lbl.pack(side=tk.LEFT, padx=(10, 8), pady=10)

        text_frame = tk.Frame(frame, bg=C_SIDEBAR)
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=8)
        name_lbl = tk.Label(text_frame, text=cat.name, font=FONT_SM,
                            fg=C_SIDEBAR_TEXT, bg=C_SIDEBAR, anchor=tk.W)
        name_lbl.pack(fill=tk.X)
        self._size_lbl = tk.Label(text_frame, text="", font=("Helvetica Neue", 10),
                                  fg="#5A5D72", bg=C_SIDEBAR, anchor=tk.W)
        self._size_lbl.pack(fill=tk.X)

        frame._bar = self._bar
        frame._name_lbl = name_lbl
        frame._size_lbl = self._size_lbl
        frame._idx = idx
        frame._icon_lbl = icon_lbl
        frame.bind("<Button-1>", lambda e, i=idx: self._on_side_click(i))
        icon_lbl.bind("<Button-1>", lambda e, i=idx: self._on_side_click(i))
        name_lbl.bind("<Button-1>", lambda e, i=idx: self._on_side_click(i))
        text_frame.bind("<Button-1>", lambda e, i=idx: self._on_side_click(i))
        frame.bind("<Enter>", lambda e, f=frame: self._side_hover(f))
        frame.bind("<Leave>", lambda e, f=frame: self._side_unhover(f))
        return frame

    def _side_hover(self, frame):
        if frame._bar.cget("bg") != C_ACCENT:
            frame.configure(bg=C_SIDEBAR_SEL)
            for w in frame.winfo_children():
                try:
                    w.configure(bg=C_SIDEBAR_SEL)
                except:
                    pass
                for c in w.winfo_children():
                    try:
                        c.configure(bg=C_SIDEBAR_SEL)
                    except:
                        pass

    def _side_unhover(self, frame):
        if frame._bar.cget("bg") != C_ACCENT:
            self._reset_side_bg(frame)

    def _reset_side_bg(self, frame):
        frame.configure(bg=C_SIDEBAR)
        for w in frame.winfo_children():
            try:
                w.configure(bg=C_SIDEBAR)
            except:
                pass
            for c in w.winfo_children():
                try:
                    c.configure(bg=C_SIDEBAR)
                except:
                    pass

    def _side_select(self, idx):
        for i, btn in enumerate(self.side_btns):
            bar = btn._bar
            name_lbl = btn._name_lbl
            icon_lbl = btn._icon_lbl
            size_lbl = btn._size_lbl
            if i == idx:
                bar.configure(bg=C_ACCENT)
                btn.configure(bg=C_SIDEBAR_SEL)
                name_lbl.configure(fg="white", bg=C_SIDEBAR_SEL)
                icon_lbl.configure(fg="white", bg=C_SIDEBAR_SEL)
                size_lbl.configure(bg=C_SIDEBAR_SEL)
            else:
                bar.configure(bg=C_SIDEBAR)
                self._reset_side_bg(btn)
                name_lbl.configure(fg=C_SIDEBAR_TEXT)
                icon_lbl.configure(fg=C_SIDEBAR_TEXT)

    def _on_side_click(self, idx):
        self.selected_category = idx
        self._side_select(idx)
        self._show_category(idx)

    # ── Buttons ───────────────────────────────────────────────────────────

    def _accent_btn(self, parent, text, command, bg=None):
        btn = tk.Label(parent, text=text, font=FONT_BOLD, fg="white",
                       bg=bg or C_ACCENT, padx=18, pady=8, cursor="hand2")
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.configure(bg=C_ACCENT_HOVER))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg or C_ACCENT))
        return btn

    def _outline_btn(self, parent, text, command):
        btn = tk.Label(parent, text=text, font=FONT_SM, fg=C_ACCENT,
                       bg=C_CARD_BG, padx=14, pady=6, cursor="hand2")
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.configure(bg="#EEF2FF"))
        btn.bind("<Leave>", lambda e: btn.configure(bg=C_CARD_BG))
        return btn

    # ── Display category items ───────────────────────────────────────────

    def _show_category(self, idx: int):
        cat = CATEGORIES[idx]
        color = CAT_COLORS[idx % len(CAT_COLORS)]
        self.cat_color = color
        self.cat_icon_lbl.config(text=CAT_ICONS[idx], fg=color)
        self.cat_title.config(text=cat.name, fg=color)

        if cat.scanned_count:
            self.cat_stats.config(text=f"{cat.scanned_count} items  ·  {human_size(cat.scanned_size)} total")
        else:
            self.cat_stats.config(text="No items found — run Scan first")

        # clear items
        for w in self.scrollable.winfo_children():
            w.destroy()
        self.checked_vars.clear()

        if not cat.items:
            empty = tk.Frame(self.scrollable, bg=C_CARD_BG, height=120)
            empty.pack(fill=tk.X, pady=20)
            tk.Label(empty, text="✨  Nothing to clean here", font=FONT,
                     fg=C_TEXT_SEC, bg=C_CARD_BG).place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            self.selected_lbl.config(text="")
            self.item_count_lbl.config(text="")
            self.select_btn.config(state=tk.DISABLED)
            self.clean_btn.config(state=tk.DISABLED)
            return

        for i, (path, size, hsize) in enumerate(cat.items):
            card = self._make_item_card(i, path, size, hsize, color)
            card.pack(fill=tk.X, pady=3)

        self._update_selected()
        self.select_btn.config(state=tk.NORMAL)
        self.clean_btn.config(state=tk.NORMAL)

    def _make_item_card(self, i, path, size, hsize, color):
        card = tk.Frame(self.scrollable, bg=C_CARD_BG, cursor="hand2")
        # subtle border via bottom line
        inner = tk.Frame(card, bg=C_CARD_BG)
        inner.pack(fill=tk.X, padx=16, pady=10)

        # checkbox
        var = tk.BooleanVar(value=True)
        item_id = f"item_{i}"
        self.checked_vars[item_id] = var

        cb = Checkbox(inner, checked=True, command=lambda v, vid=item_id: self._on_check(vid))
        cb.pack(side=tk.LEFT, padx=(0, 12))

        # color dot
        dot = tk.Canvas(inner, width=8, height=8, highlightthickness=0, bg=C_CARD_BG)
        dot.pack(side=tk.LEFT, padx=(0, 10))
        dot.create_oval(0, 0, 8, 8, fill=color, outline="")

        # name
        name = path.name if path.name else str(path)
        name_lbl = tk.Label(inner, text=name, font=FONT, fg=C_TEXT, bg=C_CARD_BG,
                            anchor=tk.W)
        name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # size
        sz_lbl = tk.Label(inner, text=hsize, font=FONT_BOLD, fg=color, bg=C_CARD_BG)
        sz_lbl.pack(side=tk.RIGHT, padx=(10, 0))

        # path (secondary)
        par_lbl = tk.Label(inner, text=str(path.parent), font=FONT_XS, fg=C_TEXT_SEC,
                           bg=C_CARD_BG, anchor=tk.W)
        par_lbl.pack(side=tk.RIGHT, padx=(0, 10))

        # click whole card to toggle
        def toggle(vid=item_id):
            var = self.checked_vars[vid]
            var.set(not var.get())
            self._sync_cb(vid)
            self._update_selected()

        card.bind("<Button-1>", lambda e, t=toggle: t())
        inner.bind("<Button-1>", lambda e, t=toggle: t())
        name_lbl.bind("<Button-1>", lambda e, t=toggle: t())
        par_lbl.bind("<Button-1>", lambda e, t=toggle: t())

        card._toggle = toggle
        card._cb = cb
        return card

    def _on_check(self, item_id):
        self._update_selected()

    def _sync_cb(self, item_id):
        for w in self.scrollable.winfo_children():
            pass  # canvas just redraws
        self._update_selected()

    def _update_selected(self):
        idx = self.selected_category
        if idx is None:
            return
        cat = CATEGORIES[idx]
        total = 0
        count = 0
        for i, item in enumerate(self.scrollable.winfo_children()):
            vid = f"item_{i}"
            if vid in self.checked_vars and self.checked_vars[vid].get():
                total += cat.items[i][1]
                count += 1
        self.selected_lbl.config(text=f"{human_size(total)} selected")
        self.item_count_lbl.config(text=f"({count} items)")

    def select_all(self):
        for vid, var in self.checked_vars.items():
            var.set(True)
        for i, card in enumerate(self.scrollable.winfo_children()):
            if hasattr(card, '_cb'):
                card._cb.set(True)
        self._update_selected()

    # ── Scan ──────────────────────────────────────────────────────────────

    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.config(text="⏣  Scanning…", fg=C_TEXT_SEC)
        self.clean_btn.config(state=tk.DISABLED)
        self.select_btn.config(state=tk.DISABLED)
        self.status.config(text="⏳ Scanning…")

        self.progress_frame.pack(fill=tk.X, pady=(0, 8))
        self.progress["value"] = 0
        self.scan_progress_label.config(text="Preparing…")

        def scan():
            total = len(CATEGORIES)
            for i, cat in enumerate(CATEGORIES):
                cat.items.clear()
                cat.scanned_size = 0
                cat.scanned_count = 0
                scan_category(cat)
                self.root.after(0, self._update_side_size, i)
                self.root.after(0, self._scan_progress, i + 1, total, cat.name)
            self.root.after(0, self._scan_done)

        threading.Thread(target=scan, daemon=True).start()

    def _update_side_size(self, idx):
        cat = CATEGORIES[idx]
        btn = self.side_btns[idx]
        if cat.scanned_count:
            btn._size_lbl.config(text=f"{cat.scanned_count} items  {human_size(cat.scanned_size)}")
        else:
            btn._size_lbl.config(text="")

    def _scan_progress(self, done, total, name):
        self.progress["value"] = done / total * 100
        self.scan_progress_label.config(text=f"Scanning {name}…  ({done}/{total})")

    def _scan_done(self):
        self.progress["value"] = 100
        self.scan_progress_label.config(text="✓ Scan complete")
        self.scanning = False
        self.scan_btn.config(text="⏣  Scan", fg="white")
        self.status.config(text="✓ Scan complete — select a category")
        if self.selected_category is not None:
            self._show_category(self.selected_category)
        else:
            self._on_side_click(0)

    # ── Clean ─────────────────────────────────────────────────────────────

    def clean_selected(self):
        idx = self.selected_category
        if idx is None:
            return
        cat = CATEGORIES[idx]
        cards = list(self.scrollable.winfo_children())
        to_delete: list[tuple[Path, str, int]] = []
        total_freed = 0
        for i, card in enumerate(cards):
            vid = f"item_{i}"
            if vid in self.checked_vars and self.checked_vars[vid].get():
                path, size, hsize = cat.items[i]
                to_delete.append((path, hsize, size))
                total_freed += size

        if not to_delete:
            messagebox.showinfo("Nothing Selected", "Check items to delete first.")
            return

        msg = f"Delete {len(to_delete)} item(s) ({human_size(total_freed)})?\n\n"
        for p, s, _ in to_delete[:6]:
            msg += f"  ✕  {p.name}  ({s})\n"
        if len(to_delete) > 6:
            msg += f"  … and {len(to_delete) - 6} more\n"
        if not messagebox.askyesno("Confirm Deletion", msg, icon="warning"):
            return

        self.clean_btn.config(state=tk.DISABLED)
        self.scan_btn.config(state=tk.DISABLED)
        self.select_btn.config(state=tk.DISABLED)
        self.status.config(text="⌛ Cleaning…")

        def clean():
            deleted = 0
            for path, _, _ in to_delete:
                self.root.after(0, lambda p=path: self.status.config(text=f"⌛ Deleting {p.name}…"))
                if delete_item(path):
                    deleted += 1
            self.root.after(0, self._clean_done, idx, total_freed, deleted)

        threading.Thread(target=clean, daemon=True).start()

    def _clean_done(self, idx, freed, deleted):
        self._freed_bytes += freed
        if freed:
            self.freed_badge.config(text=f"✓ {human_size(self._freed_bytes)} recovered total")
            self.root.after(4000, lambda: self.freed_badge.config(text=""))
        self.status.config(text=f"✓ Deleted {deleted} item(s)")
        messagebox.showinfo("Complete", f"Deleted {deleted} item(s)\n{human_size(freed)} recovered")

        # rescann
        cat = CATEGORIES[idx]
        def rescanned():
            scan_category(cat)
            self.root.after(0, self._update_side_size, idx)
            self.root.after(0, self._show_category, idx)
        threading.Thread(target=rescanned, daemon=True).start()

        self.clean_btn.config(state=tk.NORMAL)
        self.scan_btn.config(state=tk.NORMAL)
        self.select_btn.config(state=tk.NORMAL)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    CleanMyMacApp().run()
