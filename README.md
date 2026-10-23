# xefm-extensions

Extension packages for the [XeFM](https://github.com/crftwr/xefm) file
manager. Each folder is one package with its own `xefm-extension.toml`.

| Package | What it does |
|---|---|
| [classic-blue](classic-blue/) | A blue-background theme in the classic dual-pane look |
| [compute-hash](compute-hash/) | MD5 / SHA-1 / SHA-256 / SHA-512 / BLAKE2b digests of the selected files |
| [images-to-pdf](images-to-pdf/) | Combine the selected images into one PDF |
| [line-count](line-count/) | Lines, words and characters of the selected files and folders |
| [s3-share](s3-share/) | Copy a time-limited HTTPS link (presigned URL) to an S3 object |
| [size-date-filters](size-date-filters/) | Pane filters for large files and recently modified files |

## Installing a package

The desktop app and the terminal app share `~/.xefm`. A package installed
either way is available in both.

### With the `xefm` command

This works when XeFM was installed with pip, pipx, uv or the Homebrew formula
(`brew install crftwr/tap/xefm`), which put `xefm` on your PATH:

```bash
xefm ext install github:crftwr/xefm-extensions/<package>
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

### In the desktop app (macOS, Windows)

The desktop app does not add an `xefm` command, so install from inside XeFM:

1. Download this repository as a zip:
   [main.zip](https://github.com/crftwr/xefm-extensions/archive/refs/heads/main.zip).
   For a released version, download its tag's zip instead:
   `https://github.com/crftwr/xefm-extensions/archive/refs/tags/<id>-v<version>.zip`.
2. Extract it: put the cursor on the zip and choose **File ▸ Extract
   Archive…** (XeFM extracts into the other pane's folder), or use Finder /
   Explorer. The zip itself cannot be installed, because the packages are
   inside subfolders.
3. Open the extracted folders until you see the package's folder (for example
   `xefm-extensions-main/compute-hash`). Put the cursor on it and choose
   **Tools ▸ Advanced ▸ Install Extension…**.
4. XeFM checks the package and lists everything it adds. Choose **Install**
   (the dialog starts on Cancel). XeFM reloads its configuration and the
   package is ready.

**Tools ▸ Advanced ▸ Extensions…** shows which packages loaded, and why any
did not. Extensions run inside XeFM with your permissions, so install only
packages you trust.

## Releases

A release is a tag named `<id>-v<version>` (for example
`compute-hash-v0.1.0`). Each package's manifest names this repository in
`updates`, so an installed copy knows where its next version is.

## Writing a package

See [CLAUDE.md](CLAUDE.md). The XeFM skill for writing extensions is in
[.claude/skills/xefm/](.claude/skills/xefm/).
