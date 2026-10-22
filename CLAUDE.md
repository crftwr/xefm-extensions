# CLAUDE.md

Extension packages for [XeFM](https://github.com/crftwr/xefm), one package per
top-level folder (`compute-hash/`, …). XeFM itself lives in a separate
repository, usually checked out at `~/projects/xefm`.

## Read first

- **The XeFM skill** in `.claude/skills/xefm/`: `SKILL.md`, then
  `references/extensions.md` for anything about a package. It is the contract:
  the manifest keys, the public API (`xefm.user_api.__all__` only), and what
  `xefm ext check` enforces.
- An existing package, such as `compute-hash/`, for the layout and test style.

## Layout of a package

```
<id>/
  xefm-extension.toml   # id, version, api_version, min_xefm, homepage, updates
  README.md             # what it does, a demo GIF, install (CLI and desktop app), use
  docs/demo.gif
  pytest.ini
  <id_with_underscores>/
    actions.py          # thin: read ctx, prompt, run_task, show the result
    logic.py            # plain functions, no XeFM: what most tests exercise
  tests/
```

Start one with `xefm ext new <id>`, then drop what it does not need (for
example `settings.py` and `[settings]` when there is nothing to set).
`homepage` is `https://github.com/crftwr/xefm-extensions/tree/main/<id>` and
`updates` is `github:crftwr/xefm-extensions/<id>`. Add a row for the package to
the table in the top-level `README.md`.

## Checking against XeFM main

New packages often need API that is merged in XeFM but not released yet. The
`xefm` on PATH (Homebrew) is then too old. Check and test against main
instead, without touching the XeFM checkout:

```bash
X=<scratch>/xefm-main; mkdir -p $X
git -C ~/projects/xefm fetch -q
git -C ~/projects/xefm archive origin/main xefm | tar -x -C $X
PY=~/projects/xefm/.venv/bin/python          # has puikit, pyte, quality_loop
PYTHONPATH=$X $PY -m xefm ext check <id>
(cd <id> && PYTHONPATH=$X $PY -m pytest tests -q -p no:cacheprovider)
```

Main's version may still be the last release, so `min_xefm` set to the coming
release gives one expected error (`needs XeFM 1.9.0; this is 1.8.0`). Every
other line must be fixed. Remove `__pycache__` folders before committing.

## Code rules that bit us

- `extension(__name__)` (from `xefm.user_api`) is the package's handle for
  `state`, `settings` and `data_dir`. It works in prompt callbacks and workers
  too. `ctx.extension` no longer exists.
- Prompts (`ctx.choose`, `ctx.input`, `ctx.confirm`) return at once. The rest
  of the action goes in the callback, which runs after the action returned.
- `ctx.run_task(title, work, on_done=…, read_only=…)`: the worker touches only
  `job`. Use `job.progress(i, n, detail=name)` per item and
  `job.item_progress(read, size)` for bytes inside one large item, a few times
  a second. Never put a fake percentage in `detail`.
- `job.checkpoint()` raises on cancel. If a broad `except Exception` wraps the
  work, call `job.checkpoint()` inside it so a cancel is not swallowed.
- Build Markdown for `ctx.show_markdown` with `md_code_block` / `md_escape`;
  file names can hold anything.

## Tests

- Fakes take the real API's shape: `selected` is a method, `focused` an
  attribute.
- A fake `choose` stores its callback, and the test answers it *after* the
  action has returned, as XeFM does. That is how
  [crftwr/xefm#679](https://github.com/crftwr/xefm/issues/679) would have been
  caught.
- Patch `actions.extension` with a fake that answers only for the package's own
  modules.

## Seeing it run (live check)

Never start XeFM in this session's own terminal: it is an interactive app and
blocks. Run the **TUI in a pseudo-terminal** under a throwaway home instead.
The method is written up in
[crftwr/xefm#682](https://github.com/crftwr/xefm/issues/682).

1. Make a home in the scratch directory, and give XeFM `HOME` and
   `USERPROFILE` pointing there. Never touch the real `~/.xefm`.
2. Install a copy of the package into it:
   `HOME=$H USERPROFILE=$H PYTHONPATH=$X $PY -c "import sys; sys.argv[0]='xefm'; from xefm.app import main; main()" ext install <copy> --yes`.
   In the copy, lower `min_xefm` to main's version if needed.
3. Drive it with `quality_loop.drive` (`TerminalApp` + `Driver`, in XeFM's venv).
   Each step sends keys with an intent and gets the screen back as text. Keep
   the driver in a long-lived background process so you can choose each key
   from the last screen.

Things that cost retries:

- A fresh home opens the Keymap chooser, and the Tip of the Day appears once a
  day. Both swallow keys. Deleting `state.db` brings the Keymap chooser back.
- Selection and the highlighted menu row are colours only. Count menu rows
  from the screen and confirm the selection through the log's `Selected: …`
  lines.
- The driver waits up to 10 s for the screen to settle, and a progress dialog
  never settles. Send timed sequences (`Enter`, a 3 s pause, `Right`, `Enter`)
  in one call.
- Cancel in a progress dialog asks for confirmation, and the dialog starts on
  *Keep running*. Install Extension's dialog starts on *Cancel*.
- The TUI copies through OSC 52, so the clipboard cannot be checked in a PTY.

## Demo GIF

- Record by teeing everything the app writes to the PTY into an asciicast v2
  file (`[t, "o", data]`). Use 120×34, a demo folder with plausible files,
  and pauses between keys.
- Start the recording after startup, so the startup log's paths stay out of
  it. A same-size `SIGWINCH` does not repaint XeFM, so shrink the terminal by a
  row and grow it back. The cast header must carry the final size (34), not
  the shrunk one.
- Convert with `agg --idle-time-limit 1.5 --font-size 14 --last-frame-duration 4 demo.cast demo.gif`.
  Look at a few frames (`ffmpeg -i demo.gif -fps_mode passthrough f_%03d.png`)
  before committing. Replaying the cast through pyte up to a moment gives the
  reference screen to compare with.
- asciinema-player 3.8 lays out emoji as one cell. For a web replay, pad the
  cell after a wide character that is followed by a cursor move. `agg` needs
  nothing.
- Re-record when XeFM's UI changes what the GIF shows.

## Keeping the skill current

When XeFM main changes the extension API, regenerate the skill and commit it
on its own:

```bash
PYTHONPATH=$X $PY -m xefm ext skill --install <scratch>/skill
cp -R <scratch>/skill/xefm/. .claude/skills/xefm/
```

Then run `xefm ext check` on every package against main. Removed APIs are
reported as errors that name the replacement.

## Git and releases

- Work on a branch and open a PR. Merges are merge commits.
- In this repository, refer to XeFM issues as `crftwr/xefm#N`. A bare `#N`
  links to this repository.
- A release is a tag `<id>-v<version>` (for example `compute-hash-v0.1.0`),
  once the XeFM version in `min_xefm` is out. Bump `version` in the manifest
  for each release.
- When a package needs something XeFM lacks, or XeFM misbehaves, file an issue
  on crftwr/xefm with a reproduction, and keep any workaround small and
  commented with the issue number.
