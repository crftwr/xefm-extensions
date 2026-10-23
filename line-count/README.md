# Line Count

An [XeFM](https://github.com/crftwr/xefm) extension: count the lines, words
and characters of the selected files — or of everything in a selected folder —
and show them as a table, longest file first.

```
 293 lines  1,240 words  10,789 characters  (4 files)

│ Lines │ Words │ Characters │ File            │
│   157 │   623 │      5,563 │ pkg/logic.py    │
│    77 │   293 │      2,887 │ pkg/actions.py  │
│    58 │   314 │      2,269 │ README.md       │
│     1 │    10 │         70 │ pkg/__init__.py │
│   293 │ 1,240 │     10,789 │ Total           │

Skipped as binary (1): logo.png
```

## Install

Needs XeFM 1.9.0 or later. The desktop app and the terminal app share
`~/.xefm`, so either way below installs it for both.

**With the `xefm` command** (pip, pipx, uv or the Homebrew formula):

```bash
xefm ext install github:crftwr/xefm-extensions/line-count
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

**In the desktop app** (macOS, Windows), which has no `xefm` command:

1. Download
   [main.zip](https://github.com/crftwr/xefm-extensions/archive/refs/heads/main.zip).
   Once 0.1.0 is released, its tag's zip,
   [line-count-v0.1.0.zip](https://github.com/crftwr/xefm-extensions/archive/refs/tags/line-count-v0.1.0.zip),
   gives that exact version.
2. Extract it: put the cursor on the zip and choose **File ▸ Extract
   Archive…** (XeFM extracts into the other pane's folder), or use Finder /
   Explorer. The zip itself cannot be installed, because the package is in a
   subfolder.
3. Open the extracted folders until you see `line-count`, put the cursor on it
   and choose **Tools ▸ Advanced ▸ Install Extension…**.
4. XeFM lists what the package adds: the `count.lines` action and its menu
   items. Choose **Install** (the dialog starts on Cancel). XeFM reloads its
   configuration, and **File ▸ Count Lines…** appears.

## Use

**File ▸ Count Lines…**, the row's context menu, or the command palette
(`count.lines`).

- It counts the selected files and folders — or the item under the cursor
  when nothing is selected. A folder is counted with everything in it;
  hidden files and folders (a leading `.`, such as `.git`) inside it are
  skipped.
- Files on `ssh://`, `s3://` and inside archives are read through XeFM, the
  same as local ones.
- **Lines** are what an editor shows: a last line without a newline still
  counts (`wc -l` would not count it). **Words** are runs of non-whitespace,
  as `wc -w` counts them. **Characters** are counted after decoding as UTF-8.
- A file with a NUL byte near its start is treated as binary: it is skipped
  and listed below the table. Files that cannot be read are listed with the
  reason.
- Counting runs as a task, with Cancel and *Run in background*. It is
  read-only, so it does not wait behind a background copy.
- The totals line at the top has a **Copy** button. The table shows the 200
  longest files; the totals always include every file.

There is no default key. To bind one, add it to `KEY_BINDINGS` in
`~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    'count.lines': ['Ctrl-Shift-L'],
}
```

## Develop

```bash
xefm ext check line-count
cd line-count && python -m pytest tests
```

`tests/test_actions.py` needs XeFM importable; `tests/test_logic.py` does not.

This package uses only XeFM's public API (`xefm.user_api.__all__`), much of
which is still Preview (`API_VERSION` 0) and may change.
