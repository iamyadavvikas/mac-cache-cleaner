#!/usr/bin/env python3
"""Delete user caches — CLI & GUI modes."""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

HOME = Path.home()
CACHE_DIRS = [
    HOME / "Library" / "Caches",
    Path("/Library/Caches"),
]
CACHE_GLOBS = [
    HOME / "Library" / "Application Support" / "*" / "Cache",
    HOME / "Library" / "Application Support" / "*" / "cache",
    HOME / "Library" / "Application Support" / "*" / "Caches",
    HOME / "Library" / "Application Support" / "*" / "caches",
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
]


def get_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    pass
    except PermissionError:
        pass
    return total


def find_caches() -> list[tuple[Path, int]]:
    items: list[tuple[Path, int]] = []
    for d in CACHE_DIRS:
        if d.exists():
            size = get_size(d)
            items.append((d, size))
    for pattern in CACHE_GLOBS:
        matches = list(HOME.glob(str(pattern.relative_to(HOME))))
        for m in matches:
            if m.exists() and m not in [i[0] for i in items]:
                items.append((m, get_size(m)))
    items.sort(key=lambda x: x[1], reverse=True)
    return items


def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def delete_path(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    except PermissionError:
        subprocess.run(["sudo", "rm", "-rf", str(path)], capture_output=True)


# ── CLI mode ──────────────────────────────────────────────────────────────

def run_cli(args: argparse.Namespace) -> None:
    caches = find_caches()
    if not caches:
        print("No caches found.")
        sys.exit(0)

    print(f"{'Path':<70} {'Size':>10}")
    print("-" * 82)
    total = 0
    for path, size in caches:
        print(f"{str(path):<70} {fmt_size(size):>10}")
        total += size
    print("-" * 82)
    print(f"{'Total':<70} {fmt_size(total):>10}")

    if args.review:
        ans = input("\nDelete these caches? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            sys.exit(0)

    if not args.force and not args.review:
        ans = input("\nProceed with deletion? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            sys.exit(0)

    for path, _ in caches:
        print(f"Deleting {path} ...")
        delete_path(path)

    print("Done.")


# ── GUI mode ─────────────────────────────────────────────────────────────

class CacheCleanerGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Cache Cleaner")
        self.root.geometry("820x520")
        self.root.minsize(600, 300)

        style = ttk.Style()
        style.theme_use("aqua" if "aqua" in style.theme_names() else "default")

        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=(10, 0))
        ttk.Label(top, text="Cache Cleaner", font=("Helvetica", 16, "bold")).pack(side=tk.LEFT)
        self.scanning_label = ttk.Label(top, text="")
        self.scanning_label.pack(side=tk.RIGHT)

        # treeview
        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ("check", "path", "size")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        self.tree.heading("check", text="☐")
        self.tree.column("check", width=40, anchor=tk.CENTER)
        self.tree.heading("path", text="Path")
        self.tree.column("path", width=600)
        self.tree.heading("size", text="Size")
        self.tree.column("size", width=100, anchor=tk.E)

        vscroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<ButtonRelease-1>", self._on_click)

        # bottom bar
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.select_all_btn = ttk.Button(bottom, text="Select All", command=self.select_all)
        self.select_all_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.deselect_all_btn = ttk.Button(bottom, text="Deselect All", command=self.deselect_all)
        self.deselect_all_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.refresh_btn = ttk.Button(bottom, text="Refresh", command=self.refresh)
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.total_label = ttk.Label(bottom, text="Total: —", font=("Helvetica", 11, "bold"))
        self.total_label.pack(side=tk.LEFT, padx=(20, 0))

        self.status_label = ttk.Label(bottom, text="")
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))

        self.delete_btn = ttk.Button(bottom, text="Delete Selected", command=self.delete_selected)
        self.delete_btn.pack(side=tk.RIGHT)

        self.checked: dict[str, bool] = {}
        self.cache_data: list[tuple[Path, int]] = []

        self.refresh()

    def _on_click(self, event: tk.Event) -> None:
        col = self.tree.identify_column(event.x)
        if col == "#0" or col == "#1":
            item = self.tree.identify_row(event.y)
            if item:
                self._toggle(item)

    def _toggle(self, item: str) -> None:
        self.checked[item] = not self.checked.get(item, True)
        self.tree.set(item, "check", "☑" if self.checked[item] else "☐")
        self._update_total()

    def select_all(self) -> None:
        for item in self.tree.get_children():
            self.checked[item] = True
            self.tree.set(item, "check", "☑")
        self._update_total()

    def deselect_all(self) -> None:
        for item in self.tree.get_children():
            self.checked[item] = False
            self.tree.set(item, "check", "☐")
        self._update_total()

    def _update_total(self) -> None:
        total = sum(
            self.cache_data[i][1]
            for i, item in enumerate(self.tree.get_children())
            if self.checked.get(item, False)
        )
        count = sum(1 for v in self.checked.values() if v)
        self.total_label.config(text=f"Selected: {fmt_size(total)} ({count} items)")

    def refresh(self) -> None:
        self.scanning_label.config(text="Scanning...")
        self.refresh_btn.config(state=tk.DISABLED)
        self.delete_btn.config(state=tk.DISABLED)

        def scan():
            data = find_caches()
            self.root.after(0, self._populate, data)

        threading.Thread(target=scan, daemon=True).start()

    def _populate(self, data: list[tuple[Path, int]]) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.checked.clear()
        self.cache_data = data

        for i, (path, size) in enumerate(data):
            item = self.tree.insert("", tk.END, values=("☑", str(path), fmt_size(size)))
            self.checked[item] = True

        self._update_total()
        self.scanning_label.config(text="")
        self.refresh_btn.config(state=tk.NORMAL)
        self.delete_btn.config(state=tk.NORMAL if data else tk.DISABLED)

    def delete_selected(self) -> None:
        to_delete = [
            self.cache_data[i][0]
            for i, item in enumerate(self.tree.get_children())
            if self.checked.get(item, False)
        ]
        if not to_delete:
            messagebox.showinfo("Nothing Selected", "Select at least one cache to delete.")
            return

        total = sum(self.cache_data[i][1] for i, item in enumerate(self.tree.get_children()) if self.checked.get(item, False))
        msg = f"Delete {len(to_delete)} cache location(s) ({fmt_size(total)})?"
        if not messagebox.askyesno("Confirm Deletion", msg, icon="warning"):
            return

        self.delete_btn.config(state=tk.DISABLED)
        self.select_all_btn.config(state=tk.DISABLED)
        self.deselect_all_btn.config(state=tk.DISABLED)
        self.refresh_btn.config(state=tk.DISABLED)

        def delete_all():
            for path in to_delete:
                self.root.after(0, lambda p=path: self.status_label.config(text=f"Deleting {p.name}..."))
                delete_path(path)
            self.root.after(0, self._on_delete_done)

        threading.Thread(target=delete_all, daemon=True).start()

    def _on_delete_done(self) -> None:
        self.status_label.config(text="Done!")
        messagebox.showinfo("Complete", "Selected caches have been deleted.")
        self.refresh()

    def run(self) -> None:
        self.root.mainloop()


# ── Entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Delete user caches.")
    parser.add_argument("--gui", "-g", action="store_true", help="Launch GUI")
    parser.add_argument("--review", "-r", action="store_true", help="CLI: review before deleting")
    parser.add_argument("--force", "-f", action="store_true", help="CLI: skip confirmation")
    args = parser.parse_args()

    if args.gui:
        CacheCleanerGUI().run()
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
