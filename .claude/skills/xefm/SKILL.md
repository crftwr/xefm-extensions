---
name: xefm
description: Work with the XeFM file manager on the user's behalf — edit its configuration file (~/.xefm/config.py) and write, check and install extension packages. Use when the user wants to change how XeFM behaves or looks ("bind Ctrl-T to …", "make the editor code --wait", "add a favorite", "open .log files with less", "add an external program", "use the function-key keymap", "define a theme"), or wants a new XeFM feature that can live outside the core ("add an XeFM action that…", "make an XeFM extension", "turn my config.py action into an extension"), or asks to fix an extension that `xefm ext check` rejects.
---

# Working with XeFM

XeFM is a dual-pane file manager that runs as a desktop app (macOS, Windows)
and in the terminal (macOS, Windows, Linux). Everything the user customizes
lives in one folder, `~/.xefm/`, shared by every XeFM install on the machine:

```
~/.xefm/
  config.py          # the configuration: a Python file with `class Config:`
  extensions/        # installed extension packages (managed by `xefm ext`)
  tools/             # the user's own scripts for PROGRAMS entries
```

On Windows `~` is the user's profile folder (`C:\Users\<name>`).

## Ground rules

- **Never launch XeFM.** `xefm`, `python -m xefm` and the app itself open an
  interactive file manager that blocks until a person quits it. `xefm ext …`
  and `xefm skill` are safe: they never open a window.
- **XeFM applies a change when the user asks it to.** Finish with: run
  **Tools ▸ Reload Configuration** in XeFM, or restart it. Say which of the two
  the change needs (the config reference lists what only a restart applies).
- `xefm` may not be on PATH (`xefm --version` tells). Editing `config.py`
  never needs it; the `xefm ext …` commands do. If it is missing, tell the user
  rather than searching the disk for an XeFM to run.

## Which reference to read

| The user wants… | Read |
|---|---|
| a setting changed: keys, editor, diff tool, favorites, file associations, external programs, themes, confirmations, fonts, the keymap preset | `references/config.md` |
| a small function of their own bound to a key, in their config | `references/config.md` (*Actions*) |
| an action's exact name, or which keys a preset already uses | `references/actions.md` (generated from XeFM) |
| what a setting is called, its default, what it does | `references/config-template.md` (XeFM's template, generated) |
| a feature to package, share, or keep apart from their config; anything with settings of its own, tests, or several files | `references/extensions.md` |
| an extension fixed that `xefm ext check` rejects | `references/extensions.md` |

**`config.py` or an extension?** Edit `config.py` for the user's own settings
and for a short function only they will use. Write an extension instead when
the code is more than a screenful, needs its own settings or saved state,
should be shared or tested, or depends on another library. To move an action
from `config.py` into a package, follow *Start a package* in
`references/extensions.md`.
