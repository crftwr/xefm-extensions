"""The ``git.status`` attribute and the mark the ``git`` extra shows."""

from xefm.user_api import Cell

from xefm_git import repo

COLORS = {"M": "yellow", "A": "green", "D": "red", "R": "blue",
          "U": "orange", "?": "muted"}

_MARKS = {code: Cell(code, color=color) for code, color in COLORS.items()}


def status(directory, entries):
    """One ``git status`` for the whole folder; a letter per entry, or None
    outside a working tree."""
    if getattr(directory, "scheme", "file") != "file":
        return [None] * len(entries)
    return repo.folder_status(directory, [e.path.name for e in entries])


def mark(value, entry):
    """The status letter in its color, before the name."""
    return _MARKS.get(value, "")


def in_work_tree(path) -> bool:
    """Where the extra applies: a local folder inside a working tree."""
    if getattr(path, "scheme", "file") != "file":
        return False
    return repo.in_work_tree(path)
