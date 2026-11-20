# Changes in zosyazi

All notable changes to `zosyazi` are documented in this file.

---

## [1.1.5] - 2026-11-20

### Improved
- **Interactive Usability:** Added persistent key hints, visible filter match counts, clearer selection and clipboard details, editable cancellable prompts, detailed paste outcomes, and a scrollable delete review that warns before recursive removal.

## [1.1.4] - 2026-11-19

### Fixed
- **Multi-Level DSFS Casing Resolution (`get_dsfs_canonical_path`):** Added comprehensive recursive uppercase and qualifier fallback checking so paths like `c /dsfs/txt/lbdyck/test` seamlessly resolve to `/dsfs/txt/LBDYCK/TEST` or `/dsfs/txt/LBDYCK/test` whether they are intermediate qualifier directories, PDS libraries, or sequential files.

---

## [1.1.3] - 2026-11-19

### Fixed
- **DSFS Virtual Path & Uppercase Resolution:** Fixed path jumping (`c` and CLI argument) in `/dsfs/` to properly recognize HLQs (e.g. `/dsfs/txt/lbdyck/test` or `/dsfs/txt/LBDYCK`) as virtual directories without requiring `.pds` extensions or strict case matching.

---

## [1.1.2] - 2026-11-19

### Added
- **Intelligent EBCDIC / ASCII Auto-Detection (`decode_text_buffer`):** Enhanced preview pane and full-screen viewer with heuristic detection of EBCDIC (`cp1047`) vs. UTF-8/ASCII for `/dsfs/txt/` datasets and untagged USS files, rendering native EBCDIC MVS datasets accurately as text.

---

## [1.1.1] - 2026-11-19

### Added
- **Polyglot Shebang Execution:** Added dual-header `#!/bin/sh` / `"exec" "python3" "$0" "$@"` execution wrapper to guarantee execution via Python 3 even when invoked directly from z/OS USS shells without proper ASCII tag interpretation.
- **DSFS Status Popup:** Centered modal popup dialog (`[z/OS DSFS Loading...]`) during long-running `/dsfs/` operations (directory traversal, navigation, dataset loading, and full-screen viewing).

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
