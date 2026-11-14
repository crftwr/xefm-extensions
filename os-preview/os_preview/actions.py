"""The action os-preview contributes. Choosing the files and building the
command are plain functions (see logic.py), tested without XeFM."""

import sys

from xefm.user_api import xefm_python

from os_preview.logic import preview_command, preview_name, targets


def show(ctx):
    """Show the selected files in the OS preview (Quick Look on macOS).

    The preview Finder opens with the Space bar: it plays audio and video and
    shows Office documents, fonts and whatever else the system has a preview
    for. Works on the selected entries, or the one under the cursor. With
    several, the arrow keys step through them. Space or Esc closes the panel
    and XeFM has the keyboard again. Files on the local disk only."""
    name = preview_name(sys.platform)
    entries = ctx.pane.selected() or [ctx.pane.focused]
    paths, skipped = targets(entries)
    if not paths:
        ctx.message(f"{name}: nothing to show" if not skipped else
                    f"{name}: only files on the local disk can be shown")
        return
    launch = preview_command(sys.platform, paths, python=xefm_python)
    if launch is None:
        ctx.message(f"{name}: not available on this system")
        return
    if skipped:
        ctx.message(f"{name}: left out {skipped} item(s) not on the local disk")
    command, env = launch
    ctx.run_program(command, env=env)
