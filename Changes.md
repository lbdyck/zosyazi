# Changes in zosyazi

All notable changes to `zosyazi` are documented in this file.

---

## [1.1.0] - 2026-11-19

### Added
- **Interactive z/OS File Tagging (`T`):** Added native `chtag` support to inspect and modify file tags directly from within the browser or the built-in viewer (`ISO8859-1`, `IBM-1047`, `UTF-8`, custom CCSID, or remove tag).
- **JCL Job Submission & Shell Execution (`!` / `X`):** 
  - Automatically prompts to submit `.jcl`, `.cntl`, and `.job` files as MVS batch jobs using the system `submit` command.
  - Allows running arbitrary shell commands with `%f` (relative filename) and `%F` (full path) variable substitution while cleanly suspending curses.
- **Bookmarks (`m` / `'`):** Set bookmarks (`m<key>`) and jump across directories (`'<key>`) with pre-configured quick jumps (`h` = home, `r` = `/`, `t` = `/tmp`, `d` = `/dsfs/txt`).
- **Disk Space & Filesystem Info:** Shows free filesystem space `[free:...]` in the header bar for z/OS UNIX file systems.
- **File Ownership & Group Display:** Displays `user:group` owner names (via `pwd` and `grp` mapping) in the status line.
- **Terminal Resize Handling:** Added dynamic redraw handling for `curses.KEY_RESIZE` across list, viewer, and tutorial modes.

### Performance & Optimization
- **Directory Tag Batching:** Batch-caches `ls -T` file tags for the entire directory during `refresh_dir` to dramatically reduce `fork()` / `exec()` subprocess overhead on z/OS USS.

### Changed
- Removed embedded change history from `zosyazi.py` source header into dedicated `Changes.md`.
- Updated version constant to `1.1.0`.

---

## [1.0.1] - 2026-11-19

### Added
- **Built-In Scrollable Viewer (`view_file`):** Full-screen viewer bound to `Enter` / `l` / `Right` / `v` to view files without leaving curses. Safely renders EBCDIC (`IBM-1047`), ASCII/UTF-8, binary hex dumps, and `/dsfs` datasets.
- **Parent Directory Link (`..`):** Pinned `..` entry at the top of the middle pane for convenient navigation.
- **Expanded Navigation Keys:** Added `H` and `Backspace` for moving up directories.

### Fixed
- **Editor Suspension:** Fixed `open_editor()` (`e`) to properly suspend/restore curses via `curses.def_prog_mode()` / `curses.reset_prog_mode()` and prefer ASCII-native editors (`vim`, `nano`) over `/bin/vi` when `$EDITOR` is unset.

---

## [1.0.0] - 2026-11-19

### Initial Release
- **Three-Column Miller Layout:** Parent | Current | Preview navigation.
- **z/OS `/dsfs` Awareness:** Virtual path handling for `/dsfs/txt`, `/dsfs/bin`, `/dsfs/rec` without realpath collapsing.
- **z/OS File Tag Awareness:** Tag detection via `ls -T` (`IBM-1047`, `ISO8859-1`, `UTF-8`).
- **Git Integration:** Branch name and status badges (`M`, `A`, `D`, `?`, `R`).
- **Path Arguments & Navigation:** CLI path parameter, `--cwd-file` shell wrapper support, and interactive path jumping (`c`, `~`).
- **Interactive Help:** Color-coded, scrollable F1 / `?` tutorial.
