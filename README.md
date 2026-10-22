# xefm-extensions

Extension packages for the [XeFM](https://github.com/crftwr/xefm) file
manager. Each folder is one package with its own `xefm-extension.toml`.

| Package | What it does |
|---|---|
| [compute-hash](compute-hash/) | MD5 / SHA-1 / SHA-256 / SHA-512 / BLAKE2b digests of the selected files |

Install one with `xefm ext install github:crftwr/xefm-extensions/<package>`.
A release is a tag named `<id>-v<version>` (for example `compute-hash-v0.1.0`).

The XeFM skill for writing these is in [.claude/skills/xefm/](.claude/skills/xefm/).
