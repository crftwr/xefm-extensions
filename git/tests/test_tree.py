"""``git://`` folders. Needs XeFM importable (``xefm.path_base``)."""

import pytest

pytest.importorskip("xefm.path_base")

from xefm_git import repo  # noqa: E402
from xefm_git.tree import GitPathImpl  # noqa: E402


def at(top, rev, path=""):
    return GitPathImpl(repo.uri(top, rev, path))


def names(path):
    return sorted(p.name for p in path.iterdir())


def test_the_revision_s_top_lists_its_tree(work):
    top = at(work, "HEAD")
    assert top.exists() and top.is_dir()
    assert names(top) == ["README.md", "lib", "src"]   # not the working tree's changes


def test_a_folder_and_a_file(work):
    assert names(at(work, "HEAD", "src")) == ["app.py", "old.py"]
    app = at(work, "HEAD", "src/app.py")
    assert app.exists() and not app.is_dir()
    assert app.stat().st_size == len("print('two')\n")


def test_open_reads_the_revision_s_content(work):
    with at(work, "HEAD", "src/app.py").open() as fh:
        assert fh.read() == "print('two')\n"
    with at(work, "HEAD~1", "src/app.py").open("rb") as fh:
        assert fh.read() == b"print('one')\n"


def test_branch_tag_and_commit_names(work):
    for rev in ("main", "v1", repo.commit_of(work, "HEAD")[:7]):
        assert at(work, rev, "lib/util.py").exists()


def test_a_missing_path_or_revision(work):
    assert not at(work, "HEAD", "nope.txt").exists()
    assert not at(work, "no-such-branch").exists()
    with pytest.raises(FileNotFoundError):
        at(work, "HEAD", "nope.txt").stat()


def test_parent_and_child_stay_in_the_revision(work):
    app = at(work, "HEAD~1", "src/app.py")
    assert str(app.parent) == repo.uri(work, "HEAD~1", "src")
    assert str(app.parent.parent) == repo.uri(work, "HEAD~1")


def test_writes_are_refused(work):
    with pytest.raises(OSError):
        at(work, "HEAD", "new.txt").write_text("x")


def test_a_bad_uri_is_refused():
    with pytest.raises(ValueError):
        GitPathImpl("git:///proj")
