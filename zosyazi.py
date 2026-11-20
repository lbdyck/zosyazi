#!/bin/sh
"exec" "python3" "$0" "$@"
# SPDX-License-Identifier: MIT
"""
zosyazi.py - A lightweight, zero-dependency Yazi-inspired terminal file manager
for z/OS UNIX (IBM Open Enterprise SDK for Python).

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
import pwd
import grp
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

__version__ = "1.1.5"
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
        s = str(path).rstrip("/")
        parts = [p for p in s.split("/") if p]
        # /dsfs, /dsfs/mode, and /dsfs/mode/HLQ are virtual directory levels
        if len(parts) <= 3:
            return True
        # Try scandir on path or its uppercase equivalent
        try:
            with os.scandir(path):
                return True
        except OSError:
            pass
        # Check uppercase candidate
        upper_p = get_dsfs_canonical_path(path)
        if upper_p != path:
            try:
                if upper_p.is_dir():
                    return True
                with os.scandir(upper_p):
                    return True
            except OSError:
                pass
    return False


def get_dsfs_canonical_path(path: Path) -> Path:
    """Resolve /dsfs paths by testing lowercase, uppercase, and uppercase-qualifier variants."""
    if not is_dsfs_path(path):
        return path
    if path.exists():
        return path

    parts = [p for p in str(path).split("/") if p]
    if len(parts) >= 3 and parts[0] == DSFS_ROOT.strip("/") and parts[1] in ("txt", "bin", "rec"):
        # e.g. parts: ['dsfs', 'txt', 'lbdyck', 'test'] -> upper qualifiers: ['dsfs', 'txt', 'LBDYCK', 'TEST']
        upper_parts = parts[:2] + [p.upper() for p in parts[2:]]
        upper_path = Path("/" + "/".join(upper_parts))
        if upper_path.exists():
            return upper_path
        # Check intermediate HLQ capitalization: e.g. /dsfs/txt/LBDYCK/test
        if len(parts) >= 4:
            hlq_upper_parts = parts[:2] + [parts[2].upper()] + parts[3:]
            hlq_upper_path = Path("/" + "/".join(hlq_upper_parts))
            if hlq_upper_path.exists():
                return hlq_upper_path
    return path


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


def get_dir_tags(directory: Path) -> dict:
    """Batch-fetch z/OS file tags for all items in a directory to minimize subprocess spawns."""
    if is_dsfs_path(directory):
        return {}
    tag_map = {}
    try:
        res = subprocess.run(
            ["ls", "-T", str(directory)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
        if res.returncode == 0 and res.stdout:
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 4:
                    tag_str = f"{parts[0]} {parts[1]} {parts[2]}"
                    filename = parts[3]
                    tag_map[str(directory / filename)] = tag_str
    except Exception:
        pass
    return tag_map


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


def decode_text_buffer(raw: bytes, tag: str = "", dsfs_mode: str = "") -> tuple[list[str] | None, str]:
    """
    Intelligently decode raw bytes into lines of text and return (lines, detected_encoding).
    If the buffer appears to be non-text binary, returns (None, "BINARY").
    """
    if not raw:
        return ["<empty dataset/file>"], "EMPTY"

    if dsfs_mode == "BIN":
        return None, "DSFS:BIN"

    # 1. Tag explicit overrides
    if "IBM-1047" in tag:
        try:
            return raw.decode("cp1047", errors="replace").splitlines(), "IBM-1047"
        except Exception:
            pass
    elif "UTF-8" in tag:
        try:
            return raw.decode("utf-8", errors="replace").splitlines(), "UTF-8"
        except Exception:
            pass
    elif "ISO8859-1" in tag or "819" in tag:
        try:
            return raw.decode("latin-1", errors="replace").splitlines(), "ISO8859-1"
        except Exception:
            pass

    # 2. Check for null bytes (likely binary)
    sample = raw[:1024]
    if b"\x00" in sample:
        # Check if nulls are just unprintable or if entire buffer is binary
        printable_ascii = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
        if printable_ascii / len(sample) < 0.3:
            return None, "BINARY"

    # 3. For /dsfs/txt or untagged files: test EBCDIC (cp1047) vs UTF-8 / ASCII heuristic
    # Count printable characters in UTF-8
    try:
        utf8_text = raw.decode("utf-8")
        utf8_printable = sum(1 for ch in utf8_text[:1024] if ch.isprintable() or ch in "\r\n\t")
        utf8_ratio = utf8_printable / max(1, len(utf8_text[:1024]))
    except UnicodeDecodeError:
        utf8_ratio = 0.0
        utf8_text = ""

    # Count printable characters in EBCDIC (cp1047)
    try:
        ebcdic_text = raw.decode("cp1047")
        ebcdic_printable = sum(1 for ch in ebcdic_text[:1024] if ch.isprintable() or ch in "\r\n\t")
        ebcdic_ratio = ebcdic_printable / max(1, len(ebcdic_text[:1024]))
    except Exception:
        ebcdic_ratio = 0.0
        ebcdic_text = ""

    # In /dsfs/txt/, MVS datasets are typically natively EBCDIC unless autoconverted
    if dsfs_mode == "TXT":
        if ebcdic_ratio > 0.70 and ebcdic_ratio >= utf8_ratio:
            return ebcdic_text.splitlines(), "EBCDIC (IBM-1047)"
        elif utf8_ratio > 0.70:
            return (utf8_text or raw.decode("utf-8", errors="replace")).splitlines(), "UTF-8/ASCII"
        elif ebcdic_ratio > utf8_ratio:
            return ebcdic_text.splitlines(), "EBCDIC (IBM-1047)"
        else:
            return raw.decode("utf-8", errors="replace").splitlines(), "UTF-8"

    # For general USS files: prefer UTF-8 unless EBCDIC is significantly higher
    if ebcdic_ratio > 0.75 and ebcdic_ratio > utf8_ratio + 0.20:
        return ebcdic_text.splitlines(), "EBCDIC (IBM-1047)"
    elif utf8_ratio > 0.50:
        return (utf8_text or raw.decode("utf-8", errors="replace")).splitlines(), "UTF-8/ASCII"
    elif ebcdic_ratio > 0.50:
        return ebcdic_text.splitlines(), "EBCDIC (IBM-1047)"

    # Fallback to UTF-8 with replacement or hex
    if b"\x00" in sample:
        return None, "BINARY"
    return raw.decode("utf-8", errors="replace").splitlines(), "UTF-8"


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
        cwd_file: str | None = None,
        initial_select: str | None = None,
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

        self.bookmarks = {
            "h": Path.home(),
            "r": Path("/"),
            "t": Path("/tmp"),
            "d": Path(DSFS_ROOT + "/txt") if Path(DSFS_ROOT).exists() else Path("/dsfs"),
        }

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
            curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLUE)   # Modal popup dialog

    def show_popup(self, title: str, message: str):
        """Draw a centered modal popup box for long-running operations."""
        h, w = self.stdscr.getmaxyx()
        if h < 8 or w < 34:
            return
        box_w = min(max(len(title), len(message)) + 8, w - 4, 60)
        box_h = 5
        top_y = max(1, (h - box_h) // 2)
        left_x = max(1, (w - box_w) // 2)

        attr = curses.color_pair(8) | curses.A_BOLD

        # Draw box background & borders
        safe_addstr(self.stdscr, top_y, left_x, "+" + ("-" * (box_w - 2)) + "+", attr)
        title_str = f" {title} "
        safe_addstr(self.stdscr, top_y, left_x + max(1, (box_w - len(title_str)) // 2), title_str, attr)

        for r in range(1, box_h - 1):
            safe_addstr(self.stdscr, top_y + r, left_x, "|" + (" " * (box_w - 2)) + "|", attr)

        safe_addstr(self.stdscr, top_y + box_h - 1, left_x, "+" + ("-" * (box_w - 2)) + "+", attr)

        # Center message text
        msg_str = message[: box_w - 4]
        msg_x = left_x + max(1, (box_w - len(msg_str)) // 2)
        safe_addstr(self.stdscr, top_y + 2, msg_x, msg_str, attr)

        self.stdscr.refresh()

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

    def refresh_dir(self, select_name: str | None = None):
        if is_dsfs_path(self.cwd):
            self.show_popup("z/OS DSFS", f"Reading {self.cwd.name or self.cwd}...")

        self.entries = self.list_dir(self.cwd, apply_filter=True)
        if self.cwd.parent != self.cwd:
            self.parent_entries = self.list_dir(self.cwd.parent, apply_filter=False)
            # Pin '..' at the top of the middle pane for easy parent navigation
            self.entries.insert(0, self.cwd / "..")
        else:
            self.parent_entries = []

        # Batch-populate tag cache for performance on z/OS
        batch_tags = get_dir_tags(self.cwd)
        self.tag_cache.update(batch_tags)

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
            if is_dsfs_path(self.cwd.parent):
                self.show_popup("z/OS DSFS", f"Loading {self.cwd.parent.name or self.cwd.parent}...")
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
        if is_dsfs_path(resolved):
            resolved = get_dsfs_canonical_path(resolved)
            # If path does not exist as-is, check if it's a valid HLQ/qualifier in uppercase
            if not resolved.exists() and not safe_is_dir(resolved):
                parts = [p for p in str(resolved).split("/") if p]
                if len(parts) >= 3 and parts[0] == DSFS_ROOT.strip("/") and parts[1] in ("txt", "bin", "rec"):
                    upper_candidate = Path("/" + "/".join(parts[:2] + [p.upper() for p in parts[2:]]))
                    if upper_candidate.exists() or safe_is_dir(upper_candidate):
                        resolved = upper_candidate

        # Check existence or directory status
        is_directory = safe_is_dir(resolved)
        exists = resolved.exists() or is_directory

        if not exists:
            # Check if parent exists and target is a file or dataset inside parent
            parent_canonical = get_dsfs_canonical_path(resolved.parent) if is_dsfs_path(resolved) else resolved.parent
            if parent_canonical.exists() or safe_is_dir(parent_canonical):
                target_upper = resolved.name.upper()
                # Check if file exists in parent with uppercase or exact name
                candidate_file = parent_canonical / resolved.name
                candidate_upper_file = parent_canonical / target_upper
                if candidate_file.exists():
                    resolved = candidate_file
                    exists = True
                    is_directory = safe_is_dir(resolved)
                elif candidate_upper_file.exists():
                    resolved = candidate_upper_file
                    exists = True
                    is_directory = safe_is_dir(resolved)

        if not exists and not is_directory:
            self.status_msg = f"Path not found: {resolved}"
            return

        self.history[str(self.cwd)] = self.cursor
        self.filter_text = ""
        if is_dsfs_path(resolved):
            self.show_popup("z/OS DSFS", f"Accessing {resolved.name or resolved}...")

        if is_directory:
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

        if dsfs:
            # Inform user if reading a /dsfs directory or dataset takes time
            self.status_msg = f"Reading DSFS: {path.name}..."

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

                tag = self.get_tag_cached(path)
                decoded_lines, enc = decode_text_buffer(raw, tag=tag, dsfs_mode=dsfs_mode)
                if decoded_lines is None:
                    lines = format_hex_preview(raw, max_lines)
                else:
                    lines = decoded_lines[:max_lines]
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

        # Header bar with version and space info
        badges = []
        if is_dsfs_path(self.cwd):
            badges.append(f"[DSFS:{get_dsfs_mode(self.cwd)}]")
        if self.git_branch:
            badges.append(f"[git:{self.git_branch}]")
        if self.filter_text:
            match_count = sum(1 for entry in self.entries if entry.name != "..")
            badges.append(f"[filter:{self.filter_text} {match_count}]")

        try:
            if not is_dsfs_path(self.cwd):
                usage = shutil.disk_usage(self.cwd)
                free_str = human_size(usage.free)
                badges.append(f"[free:{free_str}]")
        except OSError:
            pass

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

        has_filter_matches = any(entry.name != ".." for entry in self.entries)
        if not self.entries:
            empty_text = "<no matches; Esc clears>" if self.filter_text else "<empty>"
            safe_addstr(self.stdscr, 1, left_w + 2, empty_text, curses.A_DIM, mid_w - 1)
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
            if self.filter_text and not has_filter_matches and body_h > 1:
                safe_addstr(
                    self.stdscr,
                    2,
                    left_w + 2,
                    "<no matches; Esc clears>",
                    curses.A_DIM,
                    mid_w - 1,
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
                    try:
                        uname = pwd.getpwuid(st.st_uid).pw_name
                    except (KeyError, AttributeError):
                        uname = str(st.st_uid)
                    try:
                        gname = grp.getgrgid(st.st_gid).gr_name
                    except (KeyError, AttributeError):
                        gname = str(st.st_gid)
                    info = f" {mode} {uname}:{gname} {size:>6} {mtime}{tag_str}"
                except OSError:
                    info = " <stat failed>"

        extra = []
        if self.status_msg:
            extra.append(self.status_msg)
        if self.selected:
            names = sorted(path.name for path in self.selected)
            shown_names = ", ".join(names[:2])
            if len(names) > 2:
                shown_names += f", +{len(names) - 2}"
            extra.append(f"Sel:{len(names)} {shown_names}")
        if self.clipboard and self.clipboard_mode:
            names = sorted(path.name for path in self.clipboard)
            shown_names = ", ".join(names[:2])
            if len(names) > 2:
                shown_names += f", +{len(names) - 2}"
            extra.append(
                f"{self.clipboard_mode.upper()}:{len(self.clipboard)} {shown_names} -> "
                f"{self.cwd.name or self.cwd}"
            )

        footer_width = w - 1
        enter_hint = "Enter open dir" if cur and safe_is_dir(cur) else "Enter view"
        long_hint = f"j/k move | {enter_hint} | Space mark | ? help | q quit"
        short_hint = "? help | Esc clear | q quit" if self.filter_text else "? help | q quit"
        if self.filter_text:
            long_hint += " | Esc clear"
        hint = long_hint if footer_width > len(long_hint) + 8 else short_hint
        state = " | ".join(extra)
        state_width = max(0, footer_width - len(hint) - 3)
        if state and state_width:
            right_status = f"{state[:state_width]} | {hint}"
        else:
            right_status = hint[:footer_width]
        right_width = min(len(right_status), footer_width)
        info_width = max(0, footer_width - right_width - 1)
        info = info[:info_width]
        right_status = right_status[:right_width]
        full_footer = info.ljust(info_width)
        if info_width:
            full_footer += " "
        full_footer += right_status
        safe_addstr(self.stdscr, h - 1, 0, full_footer.ljust(footer_width), curses.color_pair(5))

        self.stdscr.refresh()

    def prompt(self, prompt_text: str) -> str | None:
        """Read an editable, horizontally scrolling prompt; Escape cancels it."""
        value = []
        cursor = 0
        curses.noecho()
        curses.curs_set(1)
        try:
            while True:
                h, w = self.stdscr.getmaxyx()
                if h < 1 or w < 4:
                    self.status_msg = "Prompt unavailable: terminal too small"
                    return None

                prompt_width = min(len(prompt_text), max(1, w // 2))
                visible_prompt = prompt_text
                if len(visible_prompt) > prompt_width:
                    if prompt_width > 3:
                        visible_prompt = "..." + visible_prompt[-(prompt_width - 3):]
                    else:
                        visible_prompt = visible_prompt[-prompt_width:]
                input_x = min(len(visible_prompt), w - 2)
                input_width = max(1, w - input_x - 1)
                start = max(0, cursor - input_width + 1)
                end = min(len(value), start + input_width)
                if end - start < input_width:
                    start = max(0, end - input_width)

                self.stdscr.move(h - 1, 0)
                self.stdscr.clrtoeol()
                safe_addstr(
                    self.stdscr,
                    h - 1,
                    0,
                    visible_prompt,
                    curses.color_pair(5) | curses.A_BOLD,
                )
                safe_addstr(
                    self.stdscr,
                    h - 1,
                    input_x,
                    "".join(value[start:end]),
                    curses.color_pair(5),
                    input_width,
                )
                cursor_x = input_x + min(max(0, cursor - start), input_width - 1)
                self.stdscr.move(h - 1, cursor_x)
                self.stdscr.refresh()

                key = self.stdscr.get_wch()
                if key in ("\n", "\r", curses.KEY_ENTER):
                    return "".join(value).strip()
                if key in ("\x1b", "\x03"):
                    return None
                if key in (curses.KEY_LEFT, "\x02"):
                    cursor = max(0, cursor - 1)
                elif key in (curses.KEY_RIGHT, "\x06"):
                    cursor = min(len(value), cursor + 1)
                elif key in (curses.KEY_HOME, "\x01"):
                    cursor = 0
                elif key in (curses.KEY_END, "\x05"):
                    cursor = len(value)
                elif key in (curses.KEY_BACKSPACE, "\x7f", "\x08"):
                    if cursor:
                        del value[cursor - 1]
                        cursor -= 1
                elif key == curses.KEY_DC:
                    if cursor < len(value):
                        del value[cursor]
                elif key == "\x15":
                    value.clear()
                    cursor = 0
                elif isinstance(key, str) and key.isprintable():
                    value.insert(cursor, key)
                    cursor += 1
        except curses.error as e:
            self.status_msg = f"Prompt failed: {e}"
            return None
        finally:
            curses.curs_set(0)
            curses.noecho()

    def show_tutorial(self):
        """Colored, scrollable F1 interactive tutorial."""
        content = [
            ("section", "1. NAVIGATION", ""),
            ("key", "  j / k / Up / Down  ", "Move cursor down / up"),
            ("key", "  h / H / Left / BS  ", "Go to parent directory"),
            ("key", "  l / Right / Enter  ", "Enter directory or view file (built-in)"),
            ("key", "  v                  ", "View current file in built-in viewer"),
            ("key", "  g / G              ", "Jump to top / bottom of list"),
            ("key", "  c                  ", "Change top-level path (e.g. /dsfs/txt, ~, $HOME)"),
            ("key", "  ~                  ", "Jump directly to home directory"),
            ("key", "  m<key> / '<key>    ", "Set bookmark / Jump to bookmark (h, r, t, d)"),
            ("key", "  /  then  Enter     ", "Filter current directory; Esc cancels"),
            ("key", "  Esc                ", "Clear an active filter"),
            ("key", "  .                  ", "Toggle hidden dotfiles"),
            ("blank", "", ""),
            ("section", "2. FILE OPERATIONS", ""),
            ("key", "  Space              ", "Select / deselect item (multi-select)"),
            ("key", "  y / x / p          ", "Copy (yank) / Cut / Paste"),
            ("key", "  d                  ", "Review items and confirm deletion"),
            ("key", "  r                  ", "Rename current item"),
            ("key", "  a                  ", "Create file (end name with / for directory)"),
            ("key", "  e                  ", "Open current file in $EDITOR (vim/nano/vi)"),
            ("key", "  T                  ", "Manage z/OS file tags (chtag -t/-r/etc)"),
            ("key", "  ! / X              ", "Execute shell command or submit JCL file"),
            ("text", "  Prompts: Enter accepts, Esc cancels; arrows/Home/End edit; Ctrl-U clears.", ""),
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
            ("text", "  to decode previews automatically. Batch tags cached for high performance.", ""),
            ("blank", "", ""),
            ("section", "5. EXITING", ""),
            ("key", "  q / Esc            ", "Quit; Esc clears an active filter first"),
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
            elif key == curses.KEY_RESIZE:
                continue

    def view_file(self, path: Path):
        """Built-in, scrollable full-screen file viewer (safe for ASCII/EBCDIC & /dsfs)."""
        if path.name == ".." or safe_is_dir(path):
            return

        dsfs = is_dsfs_path(path)
        dsfs_mode = get_dsfs_mode(path) if dsfs else ""
        tag = self.get_tag_cached(path)

        if dsfs:
            self.show_popup("z/OS DSFS Viewer", f"Loading dataset {path.name}...")

        try:
            with open(path, "rb") as f:
                raw = f.read(512 * 1024)  # Cap at 512 KB for responsiveness
            
            decoded_lines, enc = decode_text_buffer(raw, tag=tag, dsfs_mode=dsfs_mode)
            if decoded_lines is None:
                lines = format_hex_preview(raw, 2000)
            else:
                lines = decoded_lines
        except OSError as e:
            self.status_msg = f"View failed: {e.strerror}"
            return

        offset = 0
        while True:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            body_h = max(1, h - 2)
            max_offset = max(0, len(lines) - body_h)

            enc_info = f" [{tag or enc}]" if (tag or enc) else ""
            title = f" VIEW: {path.name}{enc_info} ({len(lines)} lines) "
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
            footer = f" j/k/PgUp/PgDn/g/G: Scroll | e: Edit | T: Tag | q/Esc/h: Back   {min(100, pct)}% "
            safe_addstr(self.stdscr, h - 1, 0, footer.ljust(w - 1), curses.color_pair(5))
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in (ord("q"), 27, ord("h"), ord("H"), curses.KEY_LEFT):
                break
            elif key == ord("e"):
                self.open_editor(path)
                break
            elif key == ord("T"):
                self.handle_chtag(path)
                tag = self.get_tag_cached(path)
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
            elif key == curses.KEY_RESIZE:
                continue

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

    def handle_chtag(self, target_path: Path | None = None):
        """Interactive z/OS chtag file tagging tool."""
        if target_path is None:
            cur = self.current_item()
            if not cur or cur.name == "..":
                return
            target = cur
        else:
            target = target_path

        if is_dsfs_path(target):
            self.status_msg = "chtag is not applicable to /dsfs paths"
            return

        current_tag = self.get_tag_cached(target) or "untagged"
        prompt_txt = f"chtag ({target.name} is {current_tag}) [1=ISO8859-1, 2=IBM-1047, 3=UTF-8, 4=Remove, 5=Custom]: "
        choice = self.prompt(prompt_txt)
        if choice is None:
            if not self.status_msg.startswith("Prompt failed:"):
                self.status_msg = "chtag cancelled"
            return
        if not choice:
            self.status_msg = "Invalid chtag option"
            return

        cmd = None
        if choice == "1":
            cmd = ["chtag", "-tc", "ISO8859-1", str(target)]
        elif choice == "2":
            cmd = ["chtag", "-tc", "IBM-1047", str(target)]
        elif choice == "3":
            cmd = ["chtag", "-tc", "UTF-8", str(target)]
        elif choice == "4":
            cmd = ["chtag", "-r", str(target)]
        elif choice == "5":
            custom_ccs = self.prompt("Enter CCSID or encoding name (e.g. IBM-1047, ISO8859-1, 819): ")
            if custom_ccs is None:
                if not self.status_msg.startswith("Prompt failed:"):
                    self.status_msg = "chtag cancelled"
                return
            if custom_ccs:
                cmd = ["chtag", "-tc", custom_ccs, str(target)]
            else:
                self.status_msg = "CCSID cannot be empty"
                return
        else:
            self.status_msg = "Invalid chtag option"
            return

        if cmd:
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0)
                if res.returncode == 0:
                    self.tag_cache.pop(str(target), None)
                    new_tag = self.get_tag_cached(target)
                    self.preview_cache = ("", [])
                    self.status_msg = f"Tagged as {new_tag or 'untagged'}"
                else:
                    err = res.stderr.strip() or res.stdout.strip() or "failed"
                    self.status_msg = f"chtag error: {err}"
            except Exception as e:
                self.status_msg = f"chtag failed: {e}"

    def handle_exec_or_submit(self):
        """Execute a shell command or submit JCL with the current file."""
        cur = self.current_item()
        if not cur or cur.name == "..":
            return

        # Check if file looks like JCL / CNTL
        is_jcl = cur.suffix.lower() in (".jcl", ".cntl", ".job")
        if is_jcl:
            ans = self.prompt(f"Submit '{cur.name}' as JCL job? (y/N/command): ")
            if ans is None:
                return
            if ans.lower() == "y":
                # Attempt z/OS submit
                submit_cmd = shutil.which("submit") or "/bin/submit"
                try:
                    res = subprocess.run([submit_cmd, str(cur)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
                    out = res.stdout.strip() or res.stderr.strip()
                    self.status_msg = f"Submit: {out[:60]}" if out else "Job submitted"
                except Exception as e:
                    self.status_msg = f"Submit failed: {e}"
                return
            elif ans and ans.lower() != "n":
                cmd_str = ans
            else:
                return
        else:
            cmd_str = self.prompt(f"Run command (%f = '{cur.name}'): ")
            if cmd_str is None or not cmd_str:
                return

        cmd_str = cmd_str.replace("%f", f'"{cur.name}"').replace("%F", f'"{str(cur)}"')

        curses.def_prog_mode()
        curses.endwin()
        try:
            print(f"\n--- Executing: {cmd_str} ---\n")
            subprocess.run(cmd_str, shell=True, cwd=str(self.cwd))
            print("\n--- Press Enter to return to zosyazi ---")
            input()
        finally:
            curses.reset_prog_mode()
            self.stdscr.keypad(True)
            curses.curs_set(0)
            self.stdscr.clear()
            self.stdscr.refresh()
            self.refresh_dir()

    def handle_bookmark_set(self):
        key = self.prompt("Set bookmark key (a-z): ")
        if key and len(key) == 1 and key.isalpha():
            self.bookmarks[key.lower()] = self.cwd
            self.status_msg = f"Bookmark '{key.lower()}' -> {self.cwd}"

    def handle_bookmark_jump(self):
        bm_list = ", ".join(f"{k}:{v.name or '/'}" for k, v in sorted(self.bookmarks.items()))
        key = self.prompt(f"Jump bookmark ({bm_list}): ")
        if key and key.lower() in self.bookmarks:
            target = self.bookmarks[key.lower()]
            self.jump_to_path(str(target))

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
        skipped = []
        failures = []
        remaining_cut = []
        for src in self.clipboard:
            dst = self.cwd / src.name
            if dst.exists():
                skipped.append(src.name)
                if self.clipboard_mode == "cut":
                    remaining_cut.append(src)
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
                failures.append(f"{src.name}: {e.strerror or e}")
                if self.clipboard_mode == "cut":
                    remaining_cut.append(src)
        if self.clipboard_mode == "cut":
            self.clipboard = remaining_cut
            if not remaining_cut:
                self.clipboard_mode = None
        self.selected.clear()
        if count:
            self.refresh_dir()

        summary = []
        if count:
            summary.append(f"Pasted {count}")
        if skipped:
            summary.append(f"skipped {len(skipped)} existing")
        if failures:
            detail = failures[0]
            if len(failures) > 1:
                detail += f" (+{len(failures) - 1} more)"
            summary.append(f"failed {len(failures)}: {detail}")
        self.status_msg = "; ".join(summary) if summary else "No items pasted"

    def confirm_delete(self, targets: list[Path]) -> bool:
        offset = 0
        while True:
            self.stdscr.erase()
            h, w = self.stdscr.getmaxyx()
            title = f" Delete {len(targets)} item(s)? "
            safe_addstr(self.stdscr, 0, 0, title.ljust(w), curses.color_pair(5) | curses.A_BOLD)
            safe_addstr(
                self.stdscr,
                1,
                0,
                "Directories will be removed recursively. y confirms; n/Esc cancels.",
                curses.A_BOLD,
                w,
            )

            body_h = max(0, h - 3)
            max_offset = max(0, len(targets) - body_h)
            offset = min(offset, max_offset)
            for idx, path in enumerate(targets[offset : offset + body_h]):
                recursive = safe_is_dir(path) and not path.is_symlink()
                suffix = " [recursive]" if recursive else ""
                name = path.name or str(path)
                safe_addstr(
                    self.stdscr,
                    2 + idx,
                    0,
                    f" {name}{suffix} ({path.parent})",
                    max_w=w,
                )

            footer = " j/k: Scroll | y: Delete | n/Esc: Cancel "
            safe_addstr(self.stdscr, h - 1, 0, footer.ljust(w), curses.color_pair(5))
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in (ord("y"), ord("Y")):
                return True
            if key in (ord("n"), ord("N"), 27):
                return False
            if key in (ord("j"), curses.KEY_DOWN):
                offset = min(max_offset, offset + 1)
            elif key in (ord("k"), curses.KEY_UP):
                offset = max(0, offset - 1)
            elif key == curses.KEY_NPAGE:
                offset = min(max_offset, offset + max(1, body_h))
            elif key == curses.KEY_PPAGE:
                offset = max(0, offset - max(1, body_h))
            elif key == curses.KEY_RESIZE:
                continue

    def handle_delete(self):
        targets = self.get_targets()
        if not targets:
            return
        if not self.confirm_delete(targets):
            self.status_msg = "Delete cancelled"
            return
        deleted = []
        failures = []
        for p in targets:
            try:
                if safe_is_dir(p) and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                deleted.append(p)
            except OSError as e:
                failures.append(f"{p.name}: {e.strerror or e}")
        self.selected.difference_update(deleted)
        if deleted:
            self.refresh_dir()
        summary = []
        if deleted:
            summary.append(f"Deleted {len(deleted)}")
        if failures:
            detail = failures[0]
            if len(failures) > 1:
                detail += f" (+{len(failures) - 1} more)"
            summary.append(f"failed {len(failures)}: {detail}")
        self.status_msg = "; ".join(summary) if summary else "Nothing deleted"

    def run(self):
        while True:
            self.draw()
            key = self.stdscr.getch()
            self.status_msg = ""

            if key == curses.KEY_RESIZE:
                continue

            elif key in (ord("q"), 27):
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

            elif key == ord("m"):
                self.handle_bookmark_set()

            elif key == ord("'"):
                self.handle_bookmark_jump()

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

            elif key == ord("T"):
                self.handle_chtag()

            elif key in (ord("!"), ord("X")):
                self.handle_exec_or_submit()

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
                new_filter = self.prompt("Filter: ")
                if new_filter is not None:
                    self.filter_text = new_filter
                    self.refresh_dir()
                    match_count = sum(1 for entry in self.entries if entry.name != "..")
                    self.status_msg = f"{match_count} match(es)" if new_filter else "Filter cleared"

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
