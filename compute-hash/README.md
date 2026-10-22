# Compute Hash

An [XeFM](https://github.com/crftwr/xefm) extension: compute the MD5, SHA-1,
SHA-256, SHA-512 or BLAKE2b digest of the selected files and show the result
in a form you can paste into `sha256sum -c`.

![Compute Hash in XeFM's terminal UI: File menu, context menu on a selection, and a cancelled 12 GB hash](docs/demo.gif)

## Install

```bash
xefm ext install github:crftwr/xefm-extensions/compute-hash
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

Needs XeFM 1.9.0 or later (it uses `ctx.run_task` with `job.item_progress`,
`ctx.show_markdown`, `extension(__name__)` and `[contributes.menus]`).

## Use

**File ▸ Compute Hash…**, the row's context menu, or the command palette
(`hash.compute`).

1. Pick the algorithm. The last one used is listed first, so `Enter` repeats
   it.
2. The selected files are hashed — or the file under the cursor when nothing
   is selected. Directories are skipped. Files on `ssh://`, `s3://` and inside
   archives are read through XeFM, the same as local ones.
3. Hashing runs as a task: a progress dialog with Cancel and *Run in
   background*, and a byte bar for the file being read. It is read-only, so
   it does not wait behind a background copy.
4. The result shows one line per file, in selection order:

   ```
   9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08  setup.exe
   e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  notes.txt
   ```

   The block's **Copy** button copies every line; select text to copy one.
   Files that could not be read are listed below the block with the reason,
   so what you copy stays valid input for `sha256sum -c` (or `md5sum -c`,
   `b2sum -c`, …).

There is no default key. To bind one, add it to `KEY_BINDINGS` in
`~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    'hash.compute': ['Ctrl-Shift-H'],
}
```

## Develop

```bash
xefm ext check compute-hash
cd compute-hash && python -m pytest tests
```

`tests/test_actions.py` needs XeFM importable; `tests/test_logic.py` does not.

This package uses only XeFM's public API (`xefm.user_api.__all__`), much of
which is still Preview (`API_VERSION` 0) and may change.
