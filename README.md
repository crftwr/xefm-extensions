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
| [unblock-files](unblock-files/) | Remove the Mark of the Web from downloaded files (Windows) |

## Installing a package

Every package needs XeFM 1.10.0 or later. The desktop app and the terminal app
share `~/.xefm`. A package installed either way is available in both.

### Inside XeFM

In the desktop app or the terminal app, choose **Tools ▸ Advanced ▸ Install
Extension…** and paste the package's source:

```text
github:crftwr/xefm-extensions/<package>
```

XeFM downloads and checks the package and lists everything it adds. Choose
**Install** (the dialog starts on Cancel). XeFM reloads its configuration and
the package is ready. For a released version, add its tag:
`github:crftwr/xefm-extensions/<package>@<package>-v<version>`.

### With the `xefm` command

This works when XeFM was installed with pip, pipx, uv or the Homebrew formula
(`brew install crftwr/tap/xefm`), which put `xefm` on your PATH:

```bash
xefm ext install github:crftwr/xefm-extensions/<package>
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

### On XeFM 1.9.0

Install a package's 0.1.0 release: add `@<package>-v0.1.0` to the source for
the `xefm` command. 1.9.0's Install Extension takes only the package under the
cursor, so in the desktop app download the tag's zip
(`https://github.com/crftwr/xefm-extensions/archive/refs/tags/<package>-v0.1.0.zip`),
extract it (**File ▸ Extract Archive…**), open the extracted folder, put the
cursor on the package's folder and choose **Tools ▸ Advanced ▸ Install
Extension…**.

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
