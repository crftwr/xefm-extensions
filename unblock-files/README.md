# Unblock Files

An [XeFM](https://github.com/crftwr/xefm) extension for Windows: remove the
"downloaded from the internet" mark from many files at once — the same as
**Properties ▸ Unblock** in Explorer, or PowerShell's `Unblock-File`.

## What the mark is

When a browser or mail program saves a file, Windows records where it came
from in a hidden part of the file, an NTFS alternate data stream named
`Zone.Identifier` (the *Mark of the Web*):

```
[ZoneTransfer]
ZoneId=3
ReferrerUrl=https://example.com/downloads
HostUrl=https://example.com/files/setup.exe
```

While it is there, SmartScreen warns before a program runs, Office opens
documents in Protected View and blocks their macros, and Explorer passes the
mark on to everything it extracts from a marked zip. Removing it removes
those protections too, so unblock only files you trust.

## Install

Needs XeFM 1.9.0 or later, on Windows. On macOS and Linux XeFM skips the
package ("not made for …").

**With the `xefm` command** (pip, pipx or uv):

```bash
xefm ext install github:crftwr/xefm-extensions/unblock-files
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

**In the desktop app** (Microsoft Store or the portable zip), which has no
`xefm` command:

1. Download
   [main.zip](https://github.com/crftwr/xefm-extensions/archive/refs/heads/main.zip).
   Once 0.1.0 is released, its tag's zip,
   [unblock-files-v0.1.0.zip](https://github.com/crftwr/xefm-extensions/archive/refs/tags/unblock-files-v0.1.0.zip),
   gives that exact version.
2. Extract it: put the cursor on the zip and choose **File ▸ Extract
   Archive…** (XeFM extracts into the other pane's folder), or use Explorer.
   The zip itself cannot be installed, because the package is in a subfolder.
3. Open the extracted folders until you see `unblock-files`, put the cursor on
   it and choose **Tools ▸ Advanced ▸ Install Extension…**.
4. XeFM lists what the package adds: the `unblock.files` action and its menu
   items. Choose **Install** (the dialog starts on Cancel). XeFM reloads its
   configuration, and **File ▸ Unblock…** appears.

## Use

1. Select the files (or put the cursor on one) and choose **File ▸
   Unblock…**, the row's context menu, or `unblock.files` in the command
   palette.
2. XeFM checks which of them carry the mark and asks, naming where they came
   from: *Unblock 2 files downloaded from dl.example.com, github.com?*
3. On **OK** the marks are removed and the result lists each file with its
   source. The files themselves are not changed.

- Folders are skipped. Files inside archives or on SSH / S3 cannot carry the
  mark and are skipped.
- Files on FAT / exFAT drives and many network shares never carry the mark;
  they are counted as "no mark".
- A file that cannot be unblocked (read-only, in use, no permission) is listed
  with the reason.

There is no default key. To bind one, add it to `KEY_BINDINGS` in
`~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    'unblock.files': ['Ctrl-Shift-B'],
}
```

## Develop

```bash
xefm ext check unblock-files
cd unblock-files && python -m pytest tests
```

The tests run on any system: on macOS and Linux a path such as
`setup.exe:Zone.Identifier` is an ordinary file name, so the stream is
simulated by a file of that name and the same code is exercised.
`tests/test_actions.py` needs XeFM importable.

This package uses only XeFM's public API (`xefm.user_api.__all__`), much of
which is still Preview (`API_VERSION` 0) and may change.
