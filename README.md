# zosyazi

**Version:** 1.1.5  
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
* **z/OS `/dsfs` Support:**
  * Handles virtual `/dsfs` HLQ directories cleanly and displays `[DSFS:TXT|BIN|REC]` badges in the header.
  * **Qualifier Auto-Filtering:** Navigating to a qualifier prefix path such as `/dsfs/txt/lbdyck/test` (via `c` or CLI startup) automatically opens `/dsfs/txt/lbdyck` with a strict prefix filter (`test.*`) to list only datasets under that qualifier (`Esc` clears the filter).
  * Previews `/dsfs/txt` as text and `/dsfs/bin` as hex + ASCII, provides centered visual status popups while accessing datasets, and skips unnecessary `git` and `ls -T` calls inside `/dsfs`.
* **Git Integration:** Displays the active branch (`[git:branch]`) in the header and color-coded status badges (`M`, `A`, `D`, `?`, `R`) next to files and parent directories.
* **z/OS UNIX Optimized Performance:** Employs batch-caching for directory tags (`ls -T <dir>`) to eliminate `fork()` / `exec()` overhead on z/OS.
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
   ```

3. *(Optional)* Install the manpage:

   ```sh
   cp zosyazi.1 /usr/local/man/man1/
   ```

---

## Usage

```sh
zosyazi.py [OPTIONS] [PATH]
```

### CLI Options

| Option | Description |
| --- | --- |
| `PATH` | Initial directory, file, or `/dsfs` qualifier path to open (defaults to `.`). Expands `~` and environment variables (e.g., `$HOME`). If a file is given, opens its parent directory with that file highlighted. If a non-existent `/dsfs/<mode>/<hlq>/<qualifier>` path is given, opens `/dsfs/<mode>/<hlq>` with a strict prefix filter (`<qualifier>.*`). |
| `--cwd-file FILE` | Write the final working directory to `FILE` on exit (used by the shell `cd`-on-exit wrapper). |
| `-V`, `--version` | Display the version number and exit. |
| `-h`, `--help` | Display CLI usage help and exit. |

### Environment Variables

| Variable | Description |
| --- | --- |
| `ZOSYAZI_DSFS` | Override the default DSFS mount point (default: `/dsfs`). |
| `EDITOR` | External editor launched when pressing `e`. If unset, `zosyazi` prefers ASCII-native `vim` or `nano` over EBCDIC `/bin/vi`. |

---

## Examples

### Browsing z/OS UNIX Directories & Files

```sh
# Open the current working directory
zosyazi.py

# Open a specific directory
zosyazi.py ~/projects/zosyazi

# Open a file's parent directory with that file pre-selected
zosyazi.py ~/.profile
```

### Browsing MVS Datasets via `/dsfs`

```sh
# Browse all datasets under an HLQ in text mode
zosyazi.py /dsfs/txt/lbdyck

# Auto-filter an HLQ to datasets starting with a qualifier (e.g., LBDYCK.TEST.*)
zosyazi.py /dsfs/txt/lbdyck/test

# Open a specific PDS directly to browse its members
zosyazi.py /dsfs/txt/lbdyck/test.pds

# Inspect datasets in binary mode (formatted Hex + ASCII preview and viewer)
zosyazi.py /dsfs/bin/lbdyck
```

### Interactive Workflows Inside `zosyazi`

* **Jump to a `/dsfs` qualifier on the fly:** Press `c`, type `/dsfs/txt/lbdyck/test`, and press `Enter`. `zosyazi` opens `/dsfs/txt/lbdyck` with `[filter:test.*]` active. Press `Esc` to clear the filter and see the full HLQ.
* **Fix an unreadable file tag:** Highlight the file, press `T`, and choose `1` (`ISO8859-1`), `2` (`IBM-1047`), `3` (`UTF-8`), `4` (remove tag), or `5` (custom CCSID). The preview pane refreshes immediately.
* **Submit JCL to JES:** Highlight any `.jcl`, `.cntl`, or `.job` file, press `!` or `X`, and answer `y` to submit it via `/bin/submit`.
* **Run a shell command on the highlighted file:** Press `!`, then enter a command using `%f` (filename) or `%F` (full path), such as `ls -laT %f` or `iconv -f IBM-1047 -t ISO8859-1 %f`.

---

## Shell Integration (`cd` on Exit)

By default, a child process cannot change your parent shell's working directory. Using `--cwd-file`, you can wrap `zosyazi.py` in a shell function so your shell automatically `cd`s to the last directory you visited when you quit.

Add the following POSIX-compatible function to your `~/.profile`, `~/.bashrc`, or `~/.zshrc` (works in z/OS `/bin/sh`, `bash`, and `zsh`):

```sh
yy() {
    _zosyazi_tmp="$(mktemp -t zosyazi-cwd.XXXXXX)"
    zosyazi.py --cwd-file="$_zosyazi_tmp" "$@"
    if [ -f "$_zosyazi_tmp" ]; then
        _zosyazi_dir="$(cat -- "$_zosyazi_tmp")"
        rm -f -- "$_zosyazi_tmp"
        if [ -n "$_zosyazi_dir" ] && [ -d "$_zosyazi_dir" ] && [ "$_zosyazi_dir" != "$PWD" ]; then
            cd -- "$_zosyazi_dir"
        fi
    fi
    unset _zosyazi_tmp _zosyazi_dir
}
```

Reload your profile (`. ~/.profile` or `source ~/.bashrc`) and launch with `yy`:

```sh
# Browse and stay in the final directory on exit
yy

# Start in /dsfs/txt/lbdyck and stay in whatever PDS/directory you quit from
yy /dsfs/txt/lbdyck
```

> **Tip (External Editors):** IBM Open Enterprise SDK for Python runs in ASCII mode. If you use `e` to edit files, set `export EDITOR=vim` or `export EDITOR=nano` (using zopen ASCII ports) in your shell profile to avoid launching EBCDIC `/bin/vi` inside an ASCII SSH session.

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
| `c` | Change path interactively (supports env vars, `~`, and `/dsfs` qualifiers) |
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

### Built-In Viewer (`v` / `Enter`)

| Key | Action |
| --- | --- |
| `j` / `k` / `Down` / `Up` | Scroll down / up one line |
| `PgDn` / `Space` / `PgUp` / `b` | Scroll down / up one page |
| `g` / `G` | Jump to top / bottom of file |
| `e` | Open current file in `$EDITOR` |
| `T` | Manage z/OS file tag (`chtag`) |
| `q` / `Esc` / `h` / `Left` | Return to directory view |

### General

| Key | Action |
| --- | --- |
| `q` / `Esc` | Quit `zosyazi` |
| `F1` / `?` | Toggle interactive tutorial |

---

## Documentation & Changes

* See [`Changes.md`](Changes.md) for full version history.
* See `man zosyazi` or [`zosyazi.1`](zosyazi.1) for the manual page.
