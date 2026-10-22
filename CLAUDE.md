# CLAUDE.md

Extension packages for [XeFM](https://github.com/crftwr/xefm), one package per
top-level folder (`compute-hash/`, …). XeFM itself is developed in
crftwr/xefm, usually checked out at `~/projects/xefm`.

**The XeFM skill in `.claude/skills/xefm/` is the contract.** Read `SKILL.md`
and `references/extensions.md` before writing or changing a package: the
workflow, the manifest, the public API and its rules, settings, dependencies,
testing basics and publishing are all there. This file covers only what the
skill does not: this repository's conventions and the tooling around it.

## Installing or updating the skill

Install the skill from the latest XeFM release, at project level, replacing
the old folder rather than unzipping on top of it:

```bash
V=$(gh release view -R crftwr/xefm --json tagName -q .tagName)   # e.g. v1.9.0
T=<scratch>/skill-$V; mkdir -p $T                                  # new and empty
curl -fL -o $T/skill.zip \
  https://github.com/crftwr/xefm/releases/download/$V/xefm-${V#v}-skill.zip
unzip -Z1 $T/skill.zip | cut -d/ -f1 | sort -u    # must print only: xefm
unzip -p $T/skill.zip xefm/SKILL.md | sed -n 2p   # must print: name: xefm
rm -rf .claude/skills/xefm && unzip -q $T/skill.zip -d .claude/skills
rm -rf $T
```

If either check prints something else, stop and say so. The zip holds only
Markdown, so nothing in it is run. Commit the skill on its own ("Update the
XeFM skill to vX.Y.Z"), then check and test every package against that
version (next section). Do not edit the skill by hand. Report mistakes in it
on crftwr/xefm.

Between releases, when a package needs API that is on XeFM's main but not
released, generate the skill from main instead:
`PYTHONPATH=$X $PY -m xefm ext skill --install <scratch>/skill` (see below for
`$X` and `$PY`), then copy `<scratch>/skill/xefm/` over `.claude/skills/xefm/`.

## Which XeFM to check against

The `xefm` on PATH (Homebrew) can lag behind a release. Check and test against
the exact version a package targets, with uv, without installing anything:

```bash
uvx --from 'xefm==1.9.0' xefm ext check <id>
(cd <id> && uv run --no-project --with 'xefm==1.9.0' --with pytest \
   python -m pytest tests -q -p no:cacheprovider)
```

For API that is only on main, export main and use XeFM's dev venv. Do not
touch the XeFM checkout itself:

```bash
X=<scratch>/xefm-main; mkdir -p $X
git -C ~/projects/xefm fetch -q
git -C ~/projects/xefm archive origin/main xefm | tar -x -C $X
PY=~/projects/xefm/.venv/bin/python      # also has puikit, pyte, quality_loop
PYTHONPATH=$X $PY -m xefm ext check <id>
```

Main's version number is still the last release's, so a `min_xefm` set to the
coming release gives one expected error (`needs XeFM 1.9.0; this is 1.8.0`).
Every other line must be fixed. Remove `__pycache__` folders before
committing.

## Repository conventions

- In the manifest, `homepage` is
  `https://github.com/crftwr/xefm-extensions/tree/main/<id>` and `updates` is
  `github:crftwr/xefm-extensions/<id>`.
- Each package's `README.md` has what it does, a demo GIF (`docs/demo.gif`),
  install with the `xefm` command *and* in the desktop app (see
  `compute-hash/README.md`), and how to use it.
- Add a row to the package table in the top-level `README.md`.
- A workaround for an XeFM gap stays small and names the crftwr/xefm issue in
  a comment.

## Tests beyond the skill

- A fake `choose` / `input` / `confirm` stores its callback, and the test
  answers it *after* the action has returned, as XeFM does. Tests that answer
  inside the call miss bugs such as crftwr/xefm#679.
- Patch `actions.extension` with a fake that answers only for the package's
  own modules (see `compute-hash/tests/test_actions.py`). Do not copy the
  skill's thin-wrapper example as it stands: it still passes `extension=` on
  `ctx` and does not run against the scaffold (crftwr/xefm#689).
- Per-item error handling with a broad `except Exception` around
  `job.checkpoint()`: call `job.checkpoint()` again in the `except`, so a
  cancel ends the task instead of being recorded as that item's error.

## Seeing it run (live check)

The skill says never to launch XeFM, and in this session's own terminal that
stands: it is an interactive app and blocks. Run the **TUI in a
pseudo-terminal** under a throwaway home instead (method:
crftwr/xefm#682):

1. Make a home in the scratch directory, and give XeFM `HOME` and
   `USERPROFILE` pointing there. Never touch the real `~/.xefm`.
2. Install a copy of the package into it with that environment
   (`xefm ext install <copy> --yes`). Lower `min_xefm` in the copy only when
   running main.
3. Drive it with `quality_loop.drive` (`TerminalApp` + `Driver`, in XeFM's dev
   venv). Each step sends keys with an intent and gets the screen back as
   text. Keep the driver in a long-lived background process, so that each key
   can be chosen from the last screen.

Things that cost retries:

- A fresh home opens the Keymap chooser, and the Tip of the Day appears once a
  day. Both swallow keys. Deleting `state.db` brings the Keymap chooser back.
- Selection and the highlighted menu row are colours only. Count menu rows
  from the screen, and confirm the selection through the log's `Selected: …`
  lines.
- The driver waits up to 10 s for the screen to settle, and a progress dialog
  never settles. Send timed sequences (`Enter`, a 3 s pause, `Right`, `Enter`)
  in one call.
- Cancel in a progress dialog asks for confirmation, and that dialog starts on
  *Keep running*. Install Extension's dialog starts on *Cancel*.
- The TUI copies through OSC 52, so the clipboard cannot be checked in a PTY.

## Demo GIF

- Record by teeing everything the app writes to the PTY into an asciicast v2
  file (`[t, "o", data]`). Use 120×34, a demo folder with plausible files, and
  pauses between keys.
- Start the recording after startup, so the startup log's paths stay out of
  it. A same-size `SIGWINCH` does not repaint XeFM, so shrink the terminal by a
  row and grow it back. The cast header must carry the final size (34), not
  the shrunk one.
- Convert with `agg --idle-time-limit 1.5 --font-size 14 --last-frame-duration 4 demo.cast demo.gif`.
  Look at a few frames (`ffmpeg -i demo.gif -fps_mode passthrough f_%03d.png`)
  before committing. Replaying the cast through pyte up to a moment gives the
  reference screen to compare against.
- asciinema-player 3.8 lays out emoji as one cell. For a web replay, pad the
  cell after a wide character that is followed by a cursor move. `agg` needs
  nothing.
- Re-record when XeFM's UI changes what the GIF shows.

## Git and releases

- Work on a branch and open a PR. Merges are merge commits.
- In this repository, write XeFM issues as `crftwr/xefm#N`. A bare `#N` links
  to this repository.
- Release a package by tagging `<id>-v<version>` once the XeFM version in its
  `min_xefm` is out. Bump `version` in the manifest for each release.
- When a package needs something XeFM lacks, or XeFM misbehaves, file an
  issue on crftwr/xefm with a reproduction.
