# Images to PDF

An [XeFM](https://github.com/crftwr/xefm) extension: combine the selected
images into one PDF, one image per page, in the order the pane lists them.

## Install

Needs XeFM 1.10.0 or later. The desktop app and the terminal app share
`~/.xefm`, so either way below installs it for both.

**Inside XeFM** (desktop app or terminal): choose **Tools ▸ Advanced ▸ Install
Extension…** and paste

```text
github:crftwr/xefm-extensions/images-to-pdf
```

XeFM downloads and checks the package and lists what it adds: the
`images-to-pdf.combine` action and its menu items. Choose **Install** (the
dialog starts on Cancel); XeFM reloads its configuration, and **File ▸ Images
to PDF…** appears.

**With the `xefm` command** (pip, pipx, uv or the Homebrew formula):

```bash
xefm ext install github:crftwr/xefm-extensions/images-to-pdf
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

**On XeFM 1.9.0**, install version 0.1.0 instead: add `@images-to-pdf-v0.1.0`
to the source for the `xefm` command. 1.9.0's Install Extension takes only the
package under the cursor, so in the app download
[images-to-pdf-v0.1.0.zip](https://github.com/crftwr/xefm-extensions/archive/refs/tags/images-to-pdf-v0.1.0.zip),
extract it (**File ▸ Extract Archive…**), open the extracted folder, put the
cursor on `images-to-pdf` and choose **Tools ▸ Advanced ▸ Install Extension…**.

It uses Pillow, which XeFM already includes, so there is nothing else to
install.

## Use

1. Open the folder with the pictures in one pane and the folder for the PDF in
   the other.
2. Select the pictures (or put the cursor on one) and choose **File ▸ Images
   to PDF…**, the row's context menu, or `images-to-pdf.combine` in the
   command palette.
3. Type the PDF's name. It starts as the first picture's name with `.pdf`;
   `.pdf` is added if you leave it off. If the file exists, XeFM asks before
   replacing it.
4. The PDF is written to the other pane's folder, and the cursor lands on it.

- Pages are in the pane's order (sort the pane first to change it). Each page
  is the image's own size, one pixel per point.
- Photos are turned upright by their EXIF orientation. Transparency is
  flattened onto white.
- Files Pillow cannot open are skipped and listed when the PDF is done.
- Pictures can be on `ssh://`, `s3://` or inside an archive. The PDF itself
  must go to a local folder.
- Every picture is held in memory until the PDF is written, so hundreds of
  large photos at once need a lot of memory. Cancel leaves no PDF behind.

There is no default key. To bind one, add it to `KEY_BINDINGS` in
`~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    'images-to-pdf.combine': ['Ctrl-Shift-P'],
}
```

## Develop

```bash
xefm ext check images-to-pdf
cd images-to-pdf && python -m pytest tests
```

The tests need Pillow; `tests/test_actions.py` also needs XeFM importable.

This package uses only XeFM's public API (`xefm.user_api.__all__`), much of
which is still Preview (`API_VERSION` 0) and may change.
