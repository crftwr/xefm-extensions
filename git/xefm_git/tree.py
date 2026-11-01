"""``git://`` — a revision of a repository as a read-only folder.

``git:///Users/me/proj#HEAD:src/main.py`` is ``src/main.py`` as HEAD has it:
the repository's top, then git's own ``<rev>:<path>``. A revision name has no
``:`` in it (git refuses one), so the first ``:`` after the ``#`` ends it; the
repository path must not hold a ``#``.

A revision's tree is read once with ``git ls-tree`` and kept, keyed by commit,
so walking it costs no process per folder. A name like HEAD or a branch is
looked up again after a few seconds, so the folder follows it as it moves."""

import io
import threading
import time
from collections import OrderedDict

from xefm.path_base import ReadOnlyPathImpl, UriStatResult

from xefm_git import repo

_lock = threading.Lock()
#: (top, commit) → _Tree. A few, since each is a whole tree's listing.
_trees: "OrderedDict[tuple[str, str], _Tree]" = OrderedDict()
_TREES_KEPT = 8
#: (top, rev) → (commit, when looked up)
_commits: dict[tuple[str, str], tuple[str, float]] = {}
_COMMIT_TTL = 3.0


class _Tree:
    """One commit's files and folders, read in one ``git ls-tree``."""

    def __init__(self, top: str, commit: str):
        self.commit = commit
        self.time = float(repo.run(top, "show", "-s", "--format=%ct", commit).strip() or 0)
        # key → (kind, size); kind is "tree", "blob" or "commit" (a submodule)
        self.items: dict[str, tuple[str, int]] = {"": ("tree", 0)}
        self.children: dict[str, list[str]] = {"": []}
        out = repo.run(top, "ls-tree", "-r", "-t", "-l", "-z", "--full-tree", commit)
        for line in out.split("\0"):
            if not line:
                continue
            meta, _, path = line.partition("\t")
            fields = meta.split()
            if len(fields) < 4:
                continue
            kind, size = fields[1], fields[3]
            self.items[path] = (kind, int(size) if size.isdigit() else 0)
            if kind != "blob":
                self.children.setdefault(path, [])
            parent, _, name = path.rpartition("/")
            self.children.setdefault(parent, []).append(name)


def _tree(top: str, rev: str) -> _Tree | None:
    """The tree ``rev`` names in ``top``, or None if it names nothing."""
    now = time.monotonic()
    with _lock:
        known = _commits.get((top, rev))
    if known is not None and now - known[1] < _COMMIT_TTL:
        commit = known[0]
    else:
        try:
            commit = repo.commit_of(top, rev)
        except repo.GitError:
            return None
        with _lock:
            _commits[(top, rev)] = (commit, now)
    with _lock:
        tree = _trees.get((top, commit))
        if tree is not None:
            _trees.move_to_end((top, commit))
            return tree
    try:
        tree = _Tree(top, commit)
    except repo.GitError:
        return None
    with _lock:
        _trees[(top, commit)] = tree
        while len(_trees) > _TREES_KEPT:
            _trees.popitem(last=False)
    return tree


class GitPathImpl(ReadOnlyPathImpl):
    """A file or folder in one revision of a repository."""

    SCHEME = "git"
    IS_REMOTE = False
    READ_ONLY_MESSAGE = ("A Git revision is read-only. Copy the file into "
                         "the working tree to change it")

    def parse_uri(self, uri: str) -> str:
        parts = repo.split_uri(uri)
        if parts is None:
            raise ValueError(f"not a git://<repository>#<revision>:<path> URI: {uri!r}")
        self.top, self.rev, key = parts
        return key

    def root_prefix(self) -> str:
        return repo.uri(self.top, self.rev)

    def _item(self):
        tree = _tree(self.top, self.rev)
        return tree, (tree.items.get(self.key) if tree is not None else None)

    def exists(self):
        return self._item()[1] is not None

    def is_dir(self):
        item = self._item()[1]
        return item is not None and item[0] != "blob"

    def iterdir(self):
        tree = _tree(self.top, self.rev)
        if tree is None:
            raise FileNotFoundError(str(self))
        for name in tree.children.get(self.key, []):
            yield self.child(name)

    def stat(self):
        tree, item = self._item()
        if item is None:
            raise FileNotFoundError(str(self))
        return UriStatResult(size=item[1], mtime=tree.time, is_dir=item[0] != "blob")

    def open(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        tree, item = self._item()
        if item is None or item[0] != "blob":
            raise FileNotFoundError(str(self))
        try:
            data = repo.run(self.top, "cat-file", "blob", f"{tree.commit}:{self.key}",
                            text=False)
        except repo.GitError as e:
            raise OSError(str(e)) from e
        raw = io.BytesIO(data)
        if "b" in mode:
            return raw
        return io.TextIOWrapper(raw, encoding=encoding or "utf-8",
                                errors=errors or "replace", newline=newline)
