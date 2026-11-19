# zosyazi

**Version:** 1.1.4
**License:** MIT

A lightweight, zero-dependency, Yazi-inspired terminal file manager written in Python 3 for **z/OS UNIX** (IBM Open Enterprise SDK for Python).

`zosyazi` brings a three-column Miller layout, Vim-style navigation, Git status badges, an interactive `chtag` tag editor, batch JCL submission, and native **z/OS `/dsfs` (Data Set File System)** awareness to z/OS UNIX using only the Python standard library (`curses`).

---

## Features

* **Three-Column Miller Layout:** View the parent directory, current directory, and a live preview pane side-by-side.
* **Built-In Full-Screen Viewer:** Safely view EBCDIC (`IBM-1047`), ASCII (`ISO8859-1`), UTF-8, binary (hex + ASCII), and `/dsfs` datasets without leaving `curses` or garbling your SSH terminal.
* **Interactive z/OS File Tagging (`T`):** Inspect and set file tags (`chtag -tc ISO8859-1`, `IBM-1047`, `UTF-8`, custom CCSID, or untag `-r`) directly from the browser or viewer.
* **Batch JCL Submission & Shell Execution (`!` / `X`):** Automatically detects `.jcl`, `.cntl`, and `.job` files and prompts to submit them to JES via `/bin/submit`. Also allows executing arbitrary shell commands with `%f` and `%F` substitutions.
* **Directory Bookmarks (`m` / `'`):** Set bookmarks with `m<letter>` and quickly jump between directories with `'<letter>` (includes predefined quick jumps for Home `h`, Root `r`, `/tmp` `t`, and `/dsfs/txt` `d`).
* **z/OS `/dsfs` Support:** Handles virtual `/dsfs` HLQ directories cleanly, displays `[DSFS:TXT|BIN|REC]` badges in the header, previews `/dsfs/txt` as text and `/dsfs/bin` as hex + ASCII, provides centered visual status popups while accessing datasets, and skips unnecessary `git` and `ls -T` calls inside `/dsfs`.
* **Git Integration:** Displays the active branch (`[git:branch]`) in the header and color-coded status badges (`M`, `A`, `D`, `?`, `R`) next to files and parent directories.
* **z/OS USS Optimized Performance:** Employs batch-caching for directory tags (`ls -T <dir>`) to eliminate `fork()` / `exec()` overhead on z/OS.
* **Interactive F1 Tutorial:** Press `F1` or `?` for a color-coded, scrollable help guide.
* **Shell `cd`-on-Exit Support:** Supports `--cwd-file` so your shell can change to the directory you were browsing when you exit.

---

## Requirements

* **z/OS UNIX** with **IBM Open Enterprise SDK for Python** (Python 3.9+ recommended).
* No third-party Python packages required (uses only the Python standard library).
* Optional: `git` in `PATH` for repository status badges; an ASCII-native editor (`vim` or `nano` from the zopen community) if you plan to edit files with `e`.

---

## Keybindings

### Navigation
| Key | Action |
| --- | --- |
| `j` / `Down` | Move cursor down |
| `k` / `Up` | Move cursor up |
| `h` / `H` / `Left` / `Backspace` | Move to parent directory (or select `..`) |
| `l` / `Right` / `Enter` | Enter directory or view file (built-in viewer) |
| `v` | View current file in built-in viewer |
| `g` / `G` | Jump to top / bottom of directory list |
| `c` | Change path interactively (supports env vars and `~`) |
| `~` | Jump directly to home directory |
| `m<key>` / `'<key>` | Set / jump to directory bookmark (`h`, `r`, `t`, `d`) |
| `/` then `Esc` | Filter directory / clear filter |
| `.` | Toggle hidden dotfiles |

### File & z/OS Operations
| Key | Action |
| --- | --- |
| `Space` | Select / deselect item (multi-select) |
| `y` / `x` / `p` | Copy (yank) / Cut / Paste items |
| `d` | Delete selected or highlighted items |
| `r` | Rename highlighted item |
| `a` | Create file (end name with `/` for directory) |
| `e` | Open highlighted file in `$EDITOR` (`vim`/`nano`/`vi`) |
| `T` | Interactive `chtag` z/OS file tagging |
| `!` or `X` | Run shell command (`%f` = file, `%F` = path) or submit JCL |

### General
| Key | Action |
| --- | --- |
| `q` / `Esc` | Quit `zosyazi` |
| `F1` / `?` | Toggle interactive tutorial |

---

## Installation

1. Copy `zosyazi.py` to a directory in your `PATH` (for example, `~/bin/zosyazi.py` or `/usr/local/bin/zosyazi`).
2. Tag the file as ASCII (if transferred from Windows/Linux) and make it executable:

   ```sh
   chtag -tc ISO8859-1 zosyazi.py
   chmod +x zosyazi.py
   ```

3. (Optional) Install the manpage:

   ```sh
   cp zosyazi.1 /usr/local/man/man1/
   ```

---

## Shell Integration (`cd` on Exit)

Add the following function to your `~/.profile` or `~/.bashrc`:

```sh
yy() {
    local tmp="$(mktemp -t zosyazi-cwd.XXXXXX)"
    zosyazi.py --cwd-file="$tmp" "$@"
    if [ -f "$tmp" ]; then
        local dir="$(cat "$tmp")"
        rm -f "$tmp"
        if [ -d "$dir" ] && [ "$dir" != "$(pwd)" ]; then
            cd "$dir"
        fi
    fi
}
```

Now typing `yy` will launch `zosyazi` and automatically `cd` to the last browsed directory when exiting.

---

## Documentation & Changes

* See [`Changes.md`](Changes.md) for full version history.
* See `man zosyazi` or [`zosyazi.1`](zosyazi.1) for the manual page.
