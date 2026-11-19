#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
zosyazi.py - A lightweight, zero-dependency Yazi-inspired terminal file manager
for z/OS UNIX (IBM Open Enterprise SDK for Python).

Version: 1.0.1

Features:
- Three-column Miller layout (Parent | Current | Preview)
- Built-in scrollable full-screen file viewer (safe for ASCII/EBCDIC & /dsfs)
- Initial path argument (directory or file) and interactive path jumping ('c', '~')
- Colored, scrollable F1 interactive tutorial
- Git branch & color-coded status badges
- z/OS /dsfs (Data Set File System) awareness (/dsfs/txt, /dsfs/bin, /dsfs/rec)
- z/OS file-tag (ls -T) aware previews for EBCDIC (IBM-1047) and ASCII/UTF-8

Change History:
- 1.0.1 (2026-11-19):
    * Added built-in scrollable full-screen file viewer (view_file) bound to
      Enter / l / Right / v so displaying files stays inside curses and safely
      handles EBCDIC (IBM-1047), ASCII/UTF-8, and /dsfs datasets.
    * Fixed open_editor() ('e') to properly suspend/restore curses via
      def_prog_mode()/reset_prog_mode() and prefer ASCII-native editors
      (vim, nano) over EBCDIC /bin/vi when $EDITOR is unset.
    * Added '..' parent-directory entry at the top of the middle pane and
      expanded move-up keys to h / H / Left / Backspace with status feedback.
    * Updated F1 tutorial to reflect built-in viewer and navigation updates.
- 1.0.0 (2026-11-19):
    * Added version constant, TUI header version display, and -V/--version flag.
    * Added MIT License and Change History.
    * Fixed /dsfs virtual HLQ directory handling via normalize_path() and
      safe_is_dir() to avoid realpath()/.resolve() collapsing virtual paths.
    * Added initial path CLI argument (directory or file) and interactive
      top-level path jumping ('c' and '~').
    * Added colored, scrollable F1 interactive tutorial.
    * Added Git branch detection and color-coded status badges (M, A, D, ?).
    * Added z/OS /dsfs awareness (/dsfs/txt, /dsfs/bin hex dump, /dsfs/rec).
    * Initial 3-column Miller layout with z/OS file-tag (ls -T) previews.

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse
import curses
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

__version__ = "1.0.1"
DSFS_ROOT = os.environ.get("ZOSYAZI_DSFS", "/dsfs").rstrip("/")


def is_dsfs_path(path: Path) -> bool:
    s = str(path)
    return s == DSFS_ROOT or s.startswith(DSFS_ROOT + "/")


def normalize_path(path: Path) -> Path:
    """Avoid realpath()/.resolve() on virtual /dsfs paths."""
    abs_p = Path(os.path.abspath(str(path)))
    if is_dsfs_path(abs_p):
        return abs_p
    try:
        return abs_p.resolve()
    except OSError:
        return abs_p


def safe_is_dir(path: Path) -> bool:
    """Check if path is a directory, handling virtual /dsfs HLQ directories."""
    if path.name == "..":
        return True
    try:
        if path.is_dir():
            return True
    except OSError:
        pass
    if is_dsfs_path(path):
        try:
            with os.scandir(path):
                return True
        except OSError:
            return False
    return False


def get_dsfs_mode(path: Path) -> str:
    """Return DSFS access mode ('TXT', 'BIN', 'REC', or 'ROOT') for a /dsfs path."""
    s = str(path)
    if s.startswith(DSFS_ROOT + "/txt"):
        return "TXT"
    if s.startswith(DSFS_ROOT + "/bin"):
        return "BIN"
    if s.startswith(DSFS_ROOT + "/rec"):
        return "REC"
    return "ROOT"


def get_zos_tag(path: Path) -> str:
    """Return the z/OS file tag (e.g., 't ISO8859-1 T=on') or '' if unavailable."""
    if path.name == "..":
        return ""
    if is_dsfs_path(path):
        return f"DSFS:{get_dsfs_mode(path)}"
    try:
        res = subprocess.run(
            ["ls", "-T", "-d", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.5,
        )
        if res.returncode == 0 and res.stdout:
            parts = res.stdout.strip().split()
            if len(parts) >= 3:
                return f"{parts[0]} {parts[1]} {parts[2]}"
    except Exception:
        pass
    return ""


def get_git_info(directory: Path):
    """
    Return (branch_name, status_map) where status_map maps Path -> 1-char code
    ('M', 'A', 'D', '?', 'R'). Returns (None, {}) outside a Git repo or in /dsfs.
    """
    if is_dsfs_path(directory):
        return None, {}
    try:
        top = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.6,
        )
        if top.returncode != 0:
            return None, {}
        repo_root = normalize_path(Path(top.stdout.strip()))

        br = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.6,
        )
        branch = br.stdout.strip() if br.returncode == 0 else "HEAD"

        st = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
        status_map = {}
        if st.returncode == 0:
            for line in st.stdout.splitlines():
                if len(line) < 4:
                    continue
                xy = line[:2]
                rel = line[3:].strip()
                if " -> " in rel:
                    rel = rel.split(" -> ")[-1]
                rel = rel.strip('"')
                full = normalize_path(repo_root / rel)

                if "?" in xy:
                    code = "?"
                elif "D" in xy:
                    code = "D"
                elif "A" in xy:
                    code = "A"
                elif "R" in xy:
                    code = "R"
                else:
                    code = "M"

                status_map[full] = code
                parent = full.parent
                while parent != repo_root.parent and str(parent).startswith(str(repo_root)):
                    if parent not in status_map:
                        status_map[parent] = "M"
                    if parent == repo_root:
                        break
                    parent = parent.parent

        return branch, status_map
    except Exception:
        return None, {}


def format_hex_preview(raw: bytes, max_lines: int) -> list:
    """Format binary bytes as an offset + hex + ASCII preview."""
    lines = ["[Binary / DSFS:BIN Hex Preview]"]
    chunk_size = 16
    for offset in range(0, min(len(raw), (max_lines - 1) * chunk_size), chunk_size):
        chunk = raw[offset : offset + chunk_size]
        hex_part = " ".join(f"{b:02X}" for b in chunk).ljust(chunk_size * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{offset:04X}: {hex_part}  {ascii_part}")
    return lines


def human_size(size: int) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


def safe_addstr(stdscr, y: int, x: int, text: str, attr: int = 0, max_w: int = None):
    """Safely write text to curses without crashing on screen edges."""
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    limit = (w - x - 1) if max_w is None else min(max_w, w - x - 1)
    if limit <= 0:
        return
    clean = "".join(ch if ch.isprintable() else " " for ch in text)
    try:
        stdscr.addstr(y, x, clean[:limit], attr)
    except curses.error:
        pass


class ZosYazi:
    def __init__(
        self,
        stdscr,
        start_dir: Path,
        cwd_file: str = None,
        initial_select: str = None,
    ):
        self.stdscr = stdscr
        self.cwd = normalize_path(start_dir)
        self.cwd_file = cwd_file

        self.show_hidden = False
        self.filter_text = ""
        self.entries = []
        self.parent_entries = []
        self.cursor = 0
        self.scroll = 0
        self.history = {}

        self.selected = set()
        self.clipboard = []
        self.clipboard_mode = None

        self.git_branch = None
        self.git_status = {}

        self.status_msg = "Press F1 or ? for tutorial"
        self.tag_cache = {}
        self.preview_cache = ("", [])

        self._init_colors()
        self.refresh_dir(select_name=initial_select)

    def _init_colors(self):
        curses.curs_set(0)
        curses.use_default_colors()
        if curses.has_colors():
            curses.init_pair(1, curses.COLOR_CYAN, -1)       # Directories / Headers
            curses.init_pair(2, curses.COLOR_GREEN, -1)      # Executables / Git Added
            curses.init_pair(3, curses.COLOR_YELLOW, -1)     # Selected / Git Modified / Keys
            curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)   # Active cursor
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Header / Footer
            curses.init_pair(6, curses.COLOR_RED, -1)        # Errors / Git Deleted / Untracked
            curses.init_pair(7, curses.COLOR_MAGENTA, -1)    # DSFS / Tags / Metadata

    def list_dir(self, directory: Path, apply_filter: bool = False):
        try:
            items = []
            with os.scandir(directory) as it:
                for entry in it:
                    name = entry.name
                    if not self.show_hidden and name.startswith("."):
                        continue
                    if apply_filter and self.filter_text:
                        if self.filter_text.lower() not in name.lower():
                            continue
                    items.append(Path(entry.path))
            items.sort(key=lambda p: (not safe_is_dir(p), p.name.lower()))
            return items
        except OSError:
            return []

    def refresh_dir(self, select_name: str = None):
        self.entries = self.list_dir(self.cwd, apply_filter=True)
        if self.cwd.parent != self.cwd:
            self.parent_entries = self.list_dir(self.cwd.parent, apply_filter=False)
            # Pin '..' at the top of the middle pane for easy parent navigation
            self.entries.insert(0, self.cwd / "..")
        else:
            self.parent_entries = []

        self.git_branch, self.git_status = get_git_info(self.cwd)

        if select_name:
            for idx, p in enumerate(self.entries):
                if p.name == select_name:
                    self.cursor = idx
                    break
            else:
                self.cursor = 0
        elif str(self.cwd) in self.history:
            self.cursor = min(self.history[str(self.cwd)], max(0, len(self.entries) - 1))
        else:
            self.cursor = 0

        self.scroll = 0
        self.preview_cache = ("", [])

    def go_up(self):
        """Move up to the parent directory."""
        if self.cwd.parent != self.cwd:
            old_name = self.cwd.name
            self.cwd = self.cwd.parent
            self.filter_text = ""
            self.refresh_dir(select_name=old_name)
            self.status_msg = f"Up to {self.cwd}"
        else:
            self.status_msg = "Already at root /"

    def jump_to_path(self, raw_path: str):
        """Change the current top-level working directory to a new path."""
        expanded = os.path.expandvars(os.path.expanduser(raw_path.strip()))
        if not expanded:
            return
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = self.cwd / candidate

        resolved = normalize_path(candidate)
        if not resolved.exists() and not safe_is_dir(resolved):
            self.status_msg = f"Path not found: {resolved}"
            return

        self.history[str(self.cwd)] = self.cursor
        self.filter_text = ""
        if safe_is_dir(resolved):
            self.cwd = resolved
            self.refresh_dir()
            self.status_msg = f"Jumped to {self.cwd}"
        else:
            self.cwd = resolved.parent
            self.refresh_dir(select_name=resolved.name)
            self.status_msg = f"Jumped to {resolved.name}"

    def current_item(self):
        if 0 <= self.cursor < len(self.entries):
            return self.entries[self.cursor]
        return None

    def get_tag_cached(self, path: Path) -> str:
        key = str(path)
        if key not in self.tag_cache:
            self.tag_cache[key] = get_zos_tag(path)
        return self.tag_cache[key]

    def get_preview(self, path: Path, max_lines: int) -> list:
        key = str(path)
        if self.preview_cache[0] == key:
            return self.preview_cache[1]

        if path.name == "..":
            lines = [f"[Parent Directory: {self.cwd.parent}]"]
            for p in self.parent_entries[: max_lines - 1]:
                suffix = "/" if safe_is_dir(p) else ""
                lines.append(f"{p.name}{suffix}")
            self.preview_cache = (key, lines)
            return lines

        lines = []
        dsfs = is_dsfs_path(path)
        dsfs_mode = get_dsfs_mode(path) if dsfs else ""

        try:
            if safe_is_dir(path):
                sub = self.list_dir(path)
                if not sub:
                    lines = ["<empty PDS/directory>" if dsfs else "<empty directory>"]
                else:
                    if dsfs:
                        lines.append(f"[DSFS:{dsfs_mode} - {len(sub)} member(s)]")
                    for p in sub[: max_lines - (1 if dsfs else 0)]:
                        suffix = "/" if safe_is_dir(p) else ""
                        lines.append(f"{p.name}{suffix}")
            else:
                with open(path, "rb") as f:
                    raw = f.read(8192)

                if not raw:
                    lines = ["<empty dataset/file>"]
                elif dsfs and dsfs_mode == "BIN":
                    lines = format_hex_preview(raw, max_lines)
                else:
                    tag = self.get_tag_cached(path)
                    if dsfs and dsfs_mode == "TXT":
                        text = raw.decode("utf-8", errors="replace")
                    elif "IBM-1047" in tag:
                        text = raw.decode("cp1047", errors="replace")
                    elif "UTF-8" in tag or "ISO8859-1" in tag:
                        text = raw.decode("utf-8", errors="replace")
                    else:
                        if b"\x00" in raw[:512]:
                            lines = format_hex_preview(raw, max_lines)
                            text = None
                        else:
                            text = raw.decode("utf-8", errors="replace")

                    if text is not None:
                        lines = text.splitlines()[:max_lines]
        except PermissionError:
            lines = ["<permission denied>"]
        except OSError as e:
            lines = [f"<error: {e.strerror}>"]

        self.preview_cache = (key, lines)
        return lines

    def entry_attr(self, path: Path, is_cursor: bool) -> int:
        if is_cursor:
            return curses.color_pair(4) | curses.A_BOLD
        if path.name == "..":
            return curses.color_pair(1) | curses.A_BOLD
        if path in self.selected:
            return curses.color_pair(3) | curses.A_BOLD
        if path.is_symlink():
            return curses.color_pair(3)
        if safe_is_dir(path):
            if is_dsfs_path(path):
                return curses.color_pair(7) | curses.A_BOLD
            return curses.color_pair(1) | curses.A_BOLD
        try:
            if not is_dsfs_path(path) and (path.stat().st_mode & stat.S_IXUSR):
                return curses.color_pair(2)
        except OSError:
            pass
        return curses.A_NORMAL

    def git_badge_attr(self, code: str, is_cursor: bool) -> int:
        if is_cursor:
            return curses.color_pair(4) | curses.A_BOLD
        if code == "M":
            return curses.color_pair(3) | curses.A_BOLD
        if code in ("A", "R"):
            return curses.color_pair(2) | curses.A_BOLD
        if code in ("D", "?"):
            return curses.color_pair(6) | curses.A_BOLD
        return curses.A_NORMAL

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 6 or w < 30:
            safe_addstr(self.stdscr, 0, 0, "Terminal too small")
            self.stdscr.refresh()
            return

        # Header bar with version
        badges = []
        if is_dsfs_path(self.cwd):
            badges.append(f"[DSFS:{get_dsfs_mode(self.cwd)}]")
        if self.git_branch:
            badges.append(f"[git:{self.git_branch}]")
        if self.filter_text:
            badges.append(f"[filter:{self.filter_text}]")

        badge_str = (" " + " ".join(badges)) if badges else ""
        header = f" zosyazi v{__version__} | {self.cwd}{badge_str}"
        safe_addstr(self.stdscr, 0, 0, header.ljust(w), curses.color_pair(5) | curses.A_BOLD)

        body_h = h - 2
        left_w = max(10, int(w * 0.20))
        mid_w = max(15, int(w * 0.35))
        right_x = left_w + mid_w + 2
        right_w = max(10, w - right_x - 1)

        for row in range(1, h - 1):
            safe_addstr(self.stdscr, row, left_w, "|", curses.A_DIM)
            safe_addstr(self.stdscr, row, left_w + mid_w + 1, "|", curses.A_DIM)

        # 1. Left Pane: Parent directory
        for i, p in enumerate(self.parent_entries[:body_h]):
            is_cur_parent = (normalize_path(p) == self.cwd)
            attr = curses.color_pair(4) if is_cur_parent else self.entry_attr(p, False)
            name = p.name + ("/" if safe_is_dir(p) else "")
            safe_addstr(self.stdscr, 1 + i, 0, f" {name}".ljust(left_w), attr, left_w)

        # 2. Middle Pane: Current directory
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + body_h:
            self.scroll = self.cursor - body_h + 1

        if not self.entries:
            safe_addstr(self.stdscr, 1, left_w + 2, "<empty>", curses.A_DIM, mid_w - 1)
        else:
            visible = self.entries[self.scroll : self.scroll + body_h]
            for idx, p in enumerate(visible):
                real_idx = self.scroll + idx
                is_cur = (real_idx == self.cursor)
                is_parent_link = (p.name == "..")
                mark = "*" if (not is_parent_link and p in self.selected) else " "
                g_code = (
                    self.git_status.get(normalize_path(p), " ")
                    if (self.git_branch and not is_parent_link)
                    else " "
                )
                suffix = "/" if safe_is_dir(p) else ""

                row = 1 + idx
                col = left_w + 1
                base_attr = self.entry_attr(p, is_cur)

                safe_addstr(self.stdscr, row, col, " " * mid_w, base_attr, mid_w)
                safe_addstr(self.stdscr, row, col, mark, base_attr, 1)

                name_offset = 1
                if self.git_branch:
                    g_attr = self.git_badge_attr(g_code, is_cur)
                    safe_addstr(self.stdscr, row, col + 1, f"{g_code} ", g_attr, 2)
                    name_offset = 3

                label = f"{p.name}{suffix}"
                safe_addstr(
                    self.stdscr,
                    row,
                    col + name_offset,
                    label,
                    base_attr,
                    mid_w - name_offset,
                )

        # 3. Right Pane: Preview
        cur = self.current_item()
        if cur:
            preview_lines = self.get_preview(cur, body_h)
            for idx, line in enumerate(preview_lines[:body_h]):
                attr = (
                    curses.color_pair(7) | curses.A_BOLD
                    if idx == 0 and line.startswith("[")
                    else curses.A_NORMAL
                )
                safe_addstr(self.stdscr, 1 + idx, right_x, line, attr, right_w)

        # Footer / Status Bar
        info = ""
        if cur:
            if cur.name == "..":
                info = f" [Parent Directory: {self.cwd.parent}]"
            else:
                try:
                    st = cur.lstat()
                    mode = stat.filemode(st.st_mode)
                    size = human_size(st.st_size)
                    mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                    tag = self.get_tag_cached(cur)
                    tag_str = f" [{tag}]" if tag else ""
                    info = f" {mode} {size:>6} {mtime}{tag_str}"
                except OSError:
                    info = " <stat failed>"

        extra = []
        if self.selected:
            extra.append(f"Sel:{len(self.selected)}")
        if self.clipboard:
            extra.append(f"{self.clipboard_mode.upper()}:{len(self.clipboard)}")
        if self.status_msg:
            extra.append(self.status_msg)

        right_status = " | ".join(extra) + " "
        pad = max(1, w - len(info) - len(right_status) - 1)
        full_footer = (info + (" " * pad) + right_status)[: w - 1]
        safe_addstr(self.stdscr, h - 1, 0, full_footer.ljust(w - 1), curses.color_pair(5))

        self.stdscr.refresh()

    def prompt(self, prompt_text: str) -> str:
        h, w = self.stdscr.getmaxyx()
        curses.echo()
        curses.curs_set(1)
        safe_addstr(self.stdscr, h - 1, 0, " " * (w - 1), curses.color_pair(5))
        safe_addstr(self.stdscr, h - 1, 0, prompt_text, curses.color_pair(5) | curses.A_BOLD)
        self.stdscr.refresh()
        try:
            raw = self.stdscr.getstr(h - 1, len(prompt_text), w - len(prompt_text) - 2)
            result = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            result = ""
        finally:
            curses.noecho()
            curses.curs_set(0)
        return result

    def show_tutorial(self):
        """Colored, scrollable F1 interactive tutorial."""
        content = [
            ("section", "1. NAVIGATION", ""),
            ("key", "  j / k / Up / Down  ", "Move cursor down / up"),
            ("key", "  h / H / Left / BS  ", "Go to parent directory (or select '..')"),
            ("key", "  l / Right / Enter  ", "Enter directory or view file (built-in)"),
            ("key", "  v                  ", "View current file in built-in viewer"),
            ("key", "  g / G              ", "Jump to top / bottom of list"),
            ("key", "  c                  ", "Change top-level path (e.g. /dsfs/txt, ~, $HOME)"),
            ("key", "  ~                  ", "Jump directly to home directory"),
            ("key", "  /  then  Esc       ", "Filter current directory / clear filter"),
            ("key", "  .                  ", "Toggle hidden dotfiles"),
            ("blank", "", ""),
            ("section", "2. FILE OPERATIONS", ""),
            ("key", "  Space              ", "Select / deselect item (multi-select)"),
            ("key", "  y / x / p          ", "Copy (yank) / Cut / Paste"),
            ("key", "  d                  ", "Delete selected items or current item"),
            ("key", "  r                  ", "Rename current item"),
            ("key", "  a                  ", "Create file (end name with / for directory)"),
            ("key", "  e                  ", "Open current file in $EDITOR (vim/nano/vi)"),
            ("blank", "", ""),
            ("section", "3. GIT STATUS BADGES", ""),
            ("git", "  M  ", "Modified file (or directory containing changes)"),
            ("git", "  A  ", "Added / staged file"),
            ("git", "  D  ", "Deleted file"),
            ("git", "  ?  ", "Untracked file"),
            ("text", "  The active branch appears in the header as [git:branch].", ""),
            ("blank", "", ""),
            ("section", "4. z/OS /dsfs & FILE TAG AWARENESS", ""),
            ("dsfs", "  /dsfs/txt  ", "MVS datasets previewed/viewed as converted text"),
            ("dsfs", "  /dsfs/bin  ", "MVS datasets previewed/viewed as Hex + ASCII"),
            ("dsfs", "  /dsfs/rec  ", "Record-oriented MVS dataset access"),
            ("text", "  Regular z/OS UNIX files use ls -T tags (IBM-1047 / ISO8859-1 / UTF-8)", ""),
            ("text", "  to decode previews automatically. Git & ls -T are skipped in /dsfs.", ""),
            ("blank", "", ""),
            ("section", "5. EXITING", ""),
            ("key", "  q / Esc            ", "Quit zosyazi (supports --cwd-file wrapper)"),
            ("key", "  F1 / ?             ", "Open or close this tutorial"),
        ]

        offset = 0
        while True:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            body_h = max(1, h - 2)

            title = f" zosyazi v{__version__} Interactive Tutorial (F1) "
            safe_addstr(self.stdscr, 0, 0, title.ljust(w), curses.color_pair(5) | curses.A_BOLD)

            visible = content[offset : offset + body_h]
            for idx, (kind, left, right) in enumerate(visible):
                row = 1 + idx
                if kind == "section":
                    safe_addstr(self.stdscr, row, 1, left, curses.color_pair(1) | curses.A_BOLD)
                elif kind == "key":
                    safe_addstr(self.stdscr, row, 1, left, curses.color_pair(3) | curses.A_BOLD)
                    safe_addstr(self.stdscr, row, 1 + len(left), right, curses.A_NORMAL)
                elif kind == "git":
                    code = left.strip()
                    g_attr = self.git_badge_attr(code, False)
                    safe_addstr(self.stdscr, row, 1, left, g_attr)
                    safe_addstr(self.stdscr, row, 1 + len(left), right, curses.A_NORMAL)
                elif kind == "dsfs":
                    safe_addstr(self.stdscr, row, 1, left, curses.color_pair(7) | curses.A_BOLD)
                    safe_addstr(self.stdscr, row, 1 + len(left), right, curses.A_NORMAL)
                elif kind == "text":
                    safe_addstr(self.stdscr, row, 1, left, curses.A_DIM)

            footer = " j/k/Arrows: Scroll | q / Esc / F1: Close Tutorial "
            safe_addstr(self.stdscr, h - 1, 0, footer.ljust(w - 1), curses.color_pair(5))
            self.stdscr.refresh()

            key = self.stdscr.getch()
            max_offset = max(0, len(content) - body_h)
            if key in (ord("q"), 27, curses.KEY_F1, ord("?")):
                break
            elif key in (ord("j"), curses.KEY_DOWN):
                offset = min(max_offset, offset + 1)
            elif key in (ord("k"), curses.KEY_UP):
                offset = max(0, offset - 1)
            elif key == curses.KEY_NPAGE:
                offset = min(max_offset, offset + body_h)
            elif key == curses.KEY_PPAGE:
                offset = max(0, offset - body_h)

    def view_file(self, path: Path):
        """Built-in, scrollable full-screen file viewer (safe for ASCII/EBCDIC & /dsfs)."""
        if path.name == ".." or safe_is_dir(path):
            return

        dsfs = is_dsfs_path(path)
        dsfs_mode = get_dsfs_mode(path) if dsfs else ""
        tag = self.get_tag_cached(path)

        try:
            with open(path, "rb") as f:
                raw = f.read(512 * 1024)  # Cap at 512 KB for responsiveness
            if not raw:
                lines = ["<empty file>"]
            elif dsfs and dsfs_mode == "BIN":
                lines = format_hex_preview(raw, 2000)
            elif dsfs and dsfs_mode == "TXT":
                lines = raw.decode("utf-8", errors="replace").splitlines()
            elif "IBM-1047" in tag:
                lines = raw.decode("cp1047", errors="replace").splitlines()
            elif "UTF-8" in tag or "ISO8859-1" in tag:
                lines = raw.decode("utf-8", errors="replace").splitlines()
            elif b"\x00" in raw[:512]:
                lines = format_hex_preview(raw, 2000)
            else:
                lines = raw.decode("utf-8", errors="replace").splitlines()
        except OSError as e:
            self.status_msg = f"View failed: {e.strerror}"
            return

        offset = 0
        while True:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            body_h = max(1, h - 2)
            max_offset = max(0, len(lines) - body_h)

            tag_info = f" [{tag}]" if tag else ""
            title = f" VIEW: {path.name}{tag_info} ({len(lines)} lines) "
            safe_addstr(self.stdscr, 0, 0, title.ljust(w), curses.color_pair(5) | curses.A_BOLD)

            for idx, line in enumerate(lines[offset : offset + body_h]):
                lineno = f"{offset + idx + 1:>5} | "
                safe_addstr(self.stdscr, 1 + idx, 0, lineno, curses.color_pair(1))
                safe_addstr(
                    self.stdscr,
                    1 + idx,
                    len(lineno),
                    line,
                    curses.A_NORMAL,
                    w - len(lineno) - 1,
                )

            pct = int(((offset + body_h) / max(1, len(lines))) * 100)
            footer = f" j/k/PgUp/PgDn/g/G: Scroll | e: Edit | q/Esc/h: Back   {min(100, pct)}% "
            safe_addstr(self.stdscr, h - 1, 0, footer.ljust(w - 1), curses.color_pair(5))
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in (ord("q"), 27, ord("h"), ord("H"), curses.KEY_LEFT):
                break
            elif key == ord("e"):
                self.open_editor(path)
                break
            elif key in (ord("j"), curses.KEY_DOWN):
                offset = min(max_offset, offset + 1)
            elif key in (ord("k"), curses.KEY_UP):
                offset = max(0, offset - 1)
            elif key in (curses.KEY_NPAGE, ord(" ")):
                offset = min(max_offset, offset + body_h)
            elif key in (curses.KEY_PPAGE, ord("b")):
                offset = max(0, offset - body_h)
            elif key == ord("g"):
                offset = 0
            elif key == ord("G"):
                offset = max_offset

    def open_editor(self, path: Path):
        if path.name == ".." or safe_is_dir(path):
            return
        editor = os.environ.get("EDITOR")
        if not editor:
            # Prefer ASCII-native zopen editors over EBCDIC /bin/vi
            for candidate in ("vim", "nano", "vi"):
                if shutil.which(candidate):
                    editor = candidate
                    break
            else:
                editor = "vi"

        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.run([editor, str(path)])
        finally:
            curses.reset_prog_mode()
            self.stdscr.keypad(True)
            curses.curs_set(0)
            self.stdscr.clear()
            self.stdscr.refresh()
            self.tag_cache.pop(str(path), None)
            self.preview_cache = ("", [])
            self.git_branch, self.git_status = get_git_info(self.cwd)

    def get_targets(self):
        if self.selected:
            return list(self.selected)
        cur = self.current_item()
        if cur and cur.name != "..":
            return [cur]
        return []

    def handle_paste(self):
        if not self.clipboard:
            self.status_msg = "Clipboard is empty"
            return
        count = 0
        for src in self.clipboard:
            dst = self.cwd / src.name
            if dst.exists():
                self.status_msg = f"Skipped existing: {src.name}"
                continue
            try:
                if self.clipboard_mode == "copy":
                    if safe_is_dir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                elif self.clipboard_mode == "cut":
                    shutil.move(str(src), str(dst))
                count += 1
            except OSError as e:
                self.status_msg = f"Error: {e.strerror}"
                return
        if self.clipboard_mode == "cut":
            self.clipboard = []
            self.clipboard_mode = None
        self.selected.clear()
        self.refresh_dir()
        self.status_msg = f"Pasted {count} item(s)"

    def handle_delete(self):
        targets = self.get_targets()
        if not targets:
            return
        ans = self.prompt(f"Delete {len(targets)} item(s)? (y/N): ")
        if ans.lower() != "y":
            self.status_msg = "Delete cancelled"
            return
        for p in targets:
            try:
                if safe_is_dir(p) and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
            except OSError as e:
                self.status_msg = f"Delete failed: {e.strerror}"
                return
        self.selected.clear()
        self.refresh_dir()
        self.status_msg = f"Deleted {len(targets)} item(s)"

    def run(self):
        while True:
            self.draw()
            key = self.stdscr.getch()
            self.status_msg = ""

            if key in (ord("q"), 27):
                if key == 27 and self.filter_text:
                    self.filter_text = ""
                    self.refresh_dir()
                    continue
                if self.cwd_file:
                    try:
                        Path(self.cwd_file).write_text(str(self.cwd), encoding="utf-8")
                    except OSError:
                        pass
                break

            elif key in (curses.KEY_F1, ord("?")):
                self.show_tutorial()

            elif key == ord("c"):
                new_path = self.prompt("Change path: ")
                if new_path:
                    self.jump_to_path(new_path)

            elif key == ord("~"):
                self.jump_to_path(str(Path.home()))

            elif key in (ord("j"), curses.KEY_DOWN):
                if self.cursor < len(self.entries) - 1:
                    self.cursor += 1
                    self.history[str(self.cwd)] = self.cursor

            elif key in (ord("k"), curses.KEY_UP):
                if self.cursor > 0:
                    self.cursor -= 1
                    self.history[str(self.cwd)] = self.cursor

            elif key == ord("g"):
                self.cursor = 0
                self.history[str(self.cwd)] = 0

            elif key == ord("G"):
                if self.entries:
                    self.cursor = len(self.entries) - 1
                    self.history[str(self.cwd)] = self.cursor

            elif key in (ord("h"), ord("H"), curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8):
                self.go_up()

            elif key in (ord("l"), curses.KEY_RIGHT, 10, 13):
                cur = self.current_item()
                if cur and cur.name == "..":
                    self.go_up()
                elif cur and safe_is_dir(cur):
                    self.history[str(self.cwd)] = self.cursor
                    self.cwd = normalize_path(cur)
                    self.filter_text = ""
                    self.refresh_dir()
                elif cur:
                    self.view_file(cur)

            elif key == ord("v"):
                cur = self.current_item()
                if cur:
                    self.view_file(cur)

            elif key == ord("e"):
                cur = self.current_item()
                if cur:
                    self.open_editor(cur)

            elif key == ord(" "):
                cur = self.current_item()
                if cur and cur.name != "..":
                    if cur in self.selected:
                        self.selected.remove(cur)
                    else:
                        self.selected.add(cur)
                    if self.cursor < len(self.entries) - 1:
                        self.cursor += 1

            elif key == ord("y"):
                targets = self.get_targets()
                if targets:
                    self.clipboard = targets
                    self.clipboard_mode = "copy"
                    self.selected.clear()
                    self.status_msg = f"Yanked {len(targets)} item(s)"

            elif key == ord("x"):
                targets = self.get_targets()
                if targets:
                    self.clipboard = targets
                    self.clipboard_mode = "cut"
                    self.selected.clear()
                    self.status_msg = f"Cut {len(targets)} item(s)"

            elif key == ord("p"):
                self.handle_paste()

            elif key == ord("d"):
                self.handle_delete()

            elif key == ord("r"):
                cur = self.current_item()
                if cur and cur.name != "..":
                    new_name = self.prompt(f"Rename '{cur.name}' to: ")
                    if new_name:
                        try:
                            cur.rename(self.cwd / new_name)
                            self.refresh_dir(select_name=new_name)
                            self.status_msg = f"Renamed to {new_name}"
                        except OSError as e:
                            self.status_msg = f"Rename failed: {e.strerror}"

            elif key == ord("a"):
                name = self.prompt("Create (end with / for dir): ")
                if name:
                    target = self.cwd / name.rstrip("/")
                    try:
                        if name.endswith("/"):
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.touch()
                        self.refresh_dir(select_name=target.name)
                        self.status_msg = f"Created {name}"
                    except OSError as e:
                        self.status_msg = f"Create failed: {e.strerror}"

            elif key == ord("/"):
                self.filter_text = self.prompt("Filter: ")
                self.refresh_dir()

            elif key == ord("."):
                self.show_hidden = not self.show_hidden
                self.refresh_dir()


def parse_args():
    parser = argparse.ArgumentParser(
        description="zosyazi - Yazi-inspired terminal file manager for z/OS UNIX."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Initial directory or file path to open (default: current directory).",
    )
    parser.add_argument(
        "--cwd-file",
        dest="cwd_file",
        default=None,
        help="Write the final working directory to this file on exit.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    expanded = os.path.expandvars(os.path.expanduser(args.path))
    target = normalize_path(Path(expanded))

    if not target.exists() and not safe_is_dir(target):
        print(f"zosyazi: path not found: {target}", file=sys.stderr)
        sys.exit(1)

    if safe_is_dir(target):
        start_dir = target
        initial_select = None
    else:
        start_dir = target.parent
        initial_select = target.name

    curses.wrapper(
        lambda stdscr: ZosYazi(
            stdscr, start_dir, cwd_file=args.cwd_file, initial_select=initial_select
        ).run()
    )


if __name__ == "__main__":
    main()