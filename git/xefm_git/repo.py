"""Running ``git`` and reading what it prints. Nothing here imports XeFM, so
the whole module is testable against a scratch repository."""

import os
import subprocess
import unicodedata
from typing import NamedTuple

#: Seconds a ``git`` call may take before its answer is given up on. A
#: listing waits for nothing, but a stuck ``git status`` in a huge tree would
#: keep a worker busy.
TIMEOUT = 10


class GitError(Exception):
    """``git`` failed, timed out or is not installed."""


def run(cwd, *args, timeout=TIMEOUT, text=True) -> str | bytes:
    """``git <args>`` in ``cwd``; its standard output. Raises GitError."""
    try:
        done = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args], cwd=str(cwd),
            capture_output=True, text=text, timeout=timeout,
            encoding="utf-8" if text else None,
            errors="surrogateescape" if text else None)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GitError(str(e)) from e
    if done.returncode != 0:
        err = done.stderr if text else done.stderr.decode("utf-8", "replace")
        raise GitError(err.strip() or f"git {args[0]} failed")
    return done.stdout


def nfc(name: str) -> str:
    """Git and the file system can disagree on how an accented name is
    composed (macOS); names are compared composed."""
    return unicodedata.normalize("NFC", name)


class WorkTree(NamedTuple):
    """Where a folder is in its repository: the top, and the folder's path
    below it (``""`` at the top, else ending in ``/``)."""
    top: str
    prefix: str


def work_tree(directory) -> WorkTree | None:
    """The working tree ``directory`` is in, or None — not in one, inside
    ``.git``, or no ``git``."""
    try:
        out = run(directory, "rev-parse", "--show-toplevel", "--show-prefix")
    except GitError:
        return None
    lines = out.split("\n")
    if len(lines) < 2 or not lines[0]:
        return None
    return WorkTree(lines[0], lines[1])


def in_work_tree(directory) -> bool:
    """Whether ``directory`` is inside a working tree, by looking for
    ``.git`` above it — no process, since it runs for every folder opened."""
    path = os.path.abspath(str(directory))
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return os.path.basename(path) != ".git"
        parent = os.path.dirname(path)
        if parent == path:
            return False
        if os.path.basename(path) == ".git":
            return False
        path = parent


# --- status ----------------------------------------------------------------- #

#: Status letters, most important first: a folder shows the first that any
#: change inside it has.
ORDER = "UMDRA?"

_CONFLICTS = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}


def letter(xy: str) -> str:
    """One letter for a porcelain ``XY`` code. Staged and unstaged are not
    told apart: a file is Modified whether or not the change is added."""
    if xy in _CONFLICTS:
        return "U"
    if xy == "??":
        return "?"
    for code in "RDA":
        if code in xy:
            return code
    if "C" in xy:
        return "A"
    return "M"


def status(top) -> list[tuple[str, str]]:
    """``(letter, path)`` for every change in the repository at ``top``,
    paths relative to it with ``/``. An untracked folder is one entry
    ending in ``/``."""
    out = run(top, "status", "--porcelain=v1", "-z", "--ignore-submodules=dirty")
    items = out.split("\0")
    changes, i = [], 0
    while i < len(items):
        item = items[i]
        i += 1
        if len(item) < 4:
            continue
        xy, path = item[:2], item[3:]
        if "R" in xy or "C" in xy:
            i += 1                      # the old path of a rename follows
        changes.append((letter(xy), path))
    return changes


def folder_status(directory, names) -> list[str | None]:
    """One letter per name in ``directory`` — the file's, or for a folder
    the most important one of the changes inside it — or None."""
    tree = work_tree(directory)
    if tree is None:
        return [None] * len(names)
    try:
        changes = run(tree.top, "status", "--porcelain=v1", "-z",
                      "--ignore-submodules=dirty", "--", tree.prefix or ".")
    except GitError:
        return [None] * len(names)
    best: dict[str, str] = {}
    items, i = changes.split("\0"), 0
    while i < len(items):
        item = items[i]
        i += 1
        if len(item) < 4:
            continue
        xy, path = item[:2], item[3:]
        if "R" in xy or "C" in xy:
            i += 1
        if not path.startswith(tree.prefix):
            continue
        name = nfc(path[len(tree.prefix):].split("/")[0])
        code = letter(xy)
        if name not in best or ORDER.index(code) < ORDER.index(best[name]):
            best[name] = code
    return [best.get(nfc(name)) for name in names]


# --- revisions -------------------------------------------------------------- #

def commit_of(top, rev: str) -> str:
    """The full commit id ``rev`` names. Raises GitError."""
    return run(top, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").strip()


def has_object(top, rev: str, path: str) -> bool:
    try:
        run(top, "cat-file", "-e", f"{rev}:{path}")
        return True
    except GitError:
        return False


class Ref(NamedTuple):
    rev: str          # what to hand git
    label: str        # what the list shows


def refs(top, recent: int = 50) -> list[Ref]:
    """HEAD, then branches, remote branches and tags, then the last
    ``recent`` commits."""
    out = [Ref("HEAD", "HEAD")]
    listing = run(top, "for-each-ref", "--sort=-committerdate",
                  "--format=%(refname)%00%(refname:short)",
                  "refs/heads", "refs/remotes", "refs/tags")
    for line in listing.splitlines():
        full, _, short = line.partition("\0")
        if full.endswith("/HEAD"):
            continue
        kind = ("branch" if full.startswith("refs/heads/") else
                "remote" if full.startswith("refs/remotes/") else "tag")
        out.append(Ref(short, f"{short}  ({kind})"))
    log = run(top, "log", f"-n{recent}", "--format=%h%x00%ad%x00%s", "--date=short")
    for line in log.splitlines():
        short, date, subject = (line.split("\0") + ["", ""])[:3]
        out.append(Ref(short, f"{short}  {date}  {subject}"))
    return out


class Commit(NamedTuple):
    """One commit of a file's history: the file's path in it, and in its
    parent (None where the commit added the file)."""
    id: str
    short: str
    date: str
    author: str
    subject: str
    path: str
    old_path: str | None

    @property
    def label(self) -> str:
        return f"{self.short}  {self.date}  {self.author}  {self.subject}"


def history(top, path: str, limit: int = 200) -> list[Commit]:
    """The commits that changed ``path`` (relative to ``top``), newest
    first, following renames."""
    out = run(top, "log", "--follow", f"-n{limit}", "--date=short",
              "--format=%x1e%H%x1f%h%x1f%ad%x1f%an%x1f%s", "--name-status",
              "--", path)
    commits = []
    for record in out.split("\x1e")[1:]:
        head, _, body = record.partition("\n")
        fields = head.split("\x1f")
        if len(fields) < 5:
            continue
        status_line = next((ln for ln in body.splitlines() if ln.strip()), "")
        parts = status_line.split("\t")
        code = parts[0][:1] if parts else ""
        if code in ("R", "C") and len(parts) >= 3:
            new, old = parts[2], parts[1]
        elif len(parts) >= 2:
            new = parts[1]
            old = None if code == "A" else new
        else:
            new, old = path, path
        commits.append(Commit(*fields[:5], new, old))
    return commits


# --- URIs ------------------------------------------------------------------- #

def _home() -> str:
    return os.path.expanduser("~").replace("\\", "/").rstrip("/")


def uri(top, rev: str, path: str = "") -> str:
    """``git://<top>#<rev>:<path>`` — git's own ``<rev>:<path>``, after the
    repository it is in. A repository in the home folder is written from
    ``~``, as the pane header writes a home folder."""
    top = str(top).replace("\\", "/")
    home = _home()
    if home and (top == home or top.startswith(home + "/")):
        top = "~" + top[len(home):]
    return f"git://{top}#{rev}:{path.strip('/')}"


def split_uri(text: str) -> tuple[str, str, str] | None:
    """``(top, rev, path)`` of a ``git://`` URI, ``top`` with ``~`` expanded,
    or None."""
    if not text.startswith("git://"):
        return None
    top, sep, rest = text[len("git://"):].partition("#")
    rev, sep2, path = rest.partition(":")
    if not sep or not sep2 or not top or not rev:
        return None
    if top == "~" or top.startswith("~/"):
        top = _home() + top[1:]
    return top, rev, path.strip("/")
