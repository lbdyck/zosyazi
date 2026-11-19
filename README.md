# zosyazi

**Version:** 1.0.1  
**License:** MIT

A lightweight, zero-dependency, Yazi-inspired terminal file manager written in Python 3 for **z/OS UNIX** (IBM Open Enterprise SDK for Python).

`zosyazi` brings a three-column Miller layout, Vim-style navigation, Git status badges, a built-in EBCDIC/ASCII-safe file viewer, and native **z/OS `/dsfs` (Data Set File System)** awareness to z/OS UNIX using only the Python standard library (`curses`).

---

## Features

* **Three-Column Miller Layout:** View the parent directory, current directory, and a live preview pane side-by-side.
* **Built-In Full-Screen Viewer:** Safely view EBCDIC (`IBM-1047`), ASCII (`ISO8859-1`), UTF-8, binary (hex + ASCII), and `/dsfs` datasets without leaving `curses` or garbling your SSH terminal.
* **z/OS File-Tag Awareness:** Automatically reads `ls -T` file tags to decode previews and full-screen views accurately.
* **z/OS `/dsfs` Support:** Handles virtual `/dsfs` HLQ directories cleanly, displays `[DSFS:TXT|BIN|REC]` badges in the header, previews `/dsfs/txt` as text and `/dsfs/bin` as hex + ASCII, and skips unnecessary `git` and `ls -T` calls inside `/dsfs`.
* **Git Integration:** Displays the active branch (`[git:branch]`) in the header and color-coded status badges (`M`, `A`, `D`, `?`, `R`) next to files and parent directories.
* **Interactive F1 Tutorial:** Press `F1` or `?` for a color-coded, scrollable help guide.
* **Shell `cd`-on-Exit Support:** Supports `--cwd-file` so your shell can change to the directory you were browsing when you exit.

---

## Requirements

* **z/OS UNIX** with **IBM Open Enterprise SDK for Python** (Python 3.9+ recommended).
* No third-party Python packages required (uses only the Python standard library).
* Optional: `git` in `PATH` for repository status badges; an ASCII-native editor (`vim` or `nano` from the zopen community) if you plan to edit files with `e`.

---

## Installation

1. Copy `zosyazi.py` to a directory in your `PATH` (for example, `~/bin/zosyazi.py` or `/usr/local/bin/zosyazi`).
2. Tag the file as ASCII (if transferred from Windows/Linux) and make it executable:

   ```sh
   chtag -tc ISO8859-1 zosyazi.py
   chmod +x zosyazi.py