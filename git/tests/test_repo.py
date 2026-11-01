"""What git prints, read: needs only ``git``."""

import os

import pytest

from xefm_git import repo


@pytest.mark.parametrize("xy, code", [
    (" M", "M"), ("M ", "M"), ("MM", "M"), ("A ", "A"), ("AM", "A"),
    (" D", "D"), ("D ", "D"), ("R ", "R"), ("RM", "R"), ("C ", "A"),
    ("UU", "U"), ("AA", "U"), ("DU", "U"), ("??", "?"), (" T", "M"),
])
def test_one_letter_per_code(xy, code):
    assert repo.letter(xy) == code


def test_status_lists_every_change_from_the_top(work):
    assert sorted(repo.status(work)) == [
        ("?", "docs/"), ("?", "notes.txt"), ("D", "README.md"),
        ("M", "src/app.py"), ("R", "src/new.py")]


def test_folder_status_at_the_top_gives_folders_their_most_important_change(work):
    names = ["src", "lib", "docs", "notes.txt", "README.md"]
    assert repo.folder_status(work, names) == ["M", None, "?", "?", "D"]


def test_folder_status_in_a_subfolder(work):
    names = ["app.py", "new.py", "old.py"]
    assert repo.folder_status(os.path.join(work, "src"), names) == ["M", "R", None]


def test_outside_a_work_tree_everything_is_none(tmp_path):
    assert repo.folder_status(tmp_path, ["a", "b"]) == [None, None]
    assert repo.work_tree(tmp_path) is None


def test_inside_dot_git_is_not_a_work_tree(work):
    assert repo.folder_status(os.path.join(work, ".git"), ["HEAD"]) == [None]
    assert not repo.in_work_tree(os.path.join(work, ".git"))
    assert not repo.in_work_tree(os.path.join(work, ".git", "refs"))


def test_in_work_tree_looks_for_dot_git_above(work, tmp_path):
    assert repo.in_work_tree(work)
    assert repo.in_work_tree(os.path.join(work, "src"))
    assert not repo.in_work_tree(tmp_path)


def test_work_tree_names_the_top_and_the_prefix(work):
    assert repo.work_tree(os.path.join(work, "src")) == (work, "src/")
    assert repo.work_tree(work) == (work, "")


def test_no_git_on_path_is_none(work, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert repo.folder_status(work, ["src"]) == [None]


def test_refs_start_with_head_then_branches_tags_and_commits(work):
    refs = repo.refs(work)
    assert refs[0] == ("HEAD", "HEAD")
    labels = [r.label for r in refs]
    assert "main  (branch)" in labels and "v1  (tag)" in labels
    assert [r.label.split("  ")[-1] for r in refs[-2:]] == ["Second", "First"]


def test_history_follows_the_file(work):
    commits = repo.history(work, "src/app.py")
    assert [c.subject for c in commits] == ["Second", "First"]
    assert commits[0].old_path == "src/app.py"
    assert commits[1].old_path is None          # added there
    assert commits[0].author == "Tester"


def test_history_through_a_rename(work):
    repo.run(work, "commit", "-q", "-m", "Rename")
    (rename, first) = repo.history(work, "src/new.py")
    assert (rename.path, rename.old_path) == ("src/new.py", "src/old.py")
    assert (first.path, first.old_path) == ("src/old.py", None)


@pytest.mark.parametrize("top, rev, path", [
    ("/Users/me/proj", "HEAD", "src/a.py"),
    ("/Users/me/proj", "feature/x", ""),
    ("C:/Users/me/proj", "HEAD~2", "a b/c.txt"),
])
def test_uris_round_trip(top, rev, path):
    assert repo.split_uri(repo.uri(top, rev, path)) == (top, rev, path)


def test_the_home_folder_is_written_as_a_tilde(monkeypatch, tmp_path):
    home = str(tmp_path).replace("\\", "/")
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("USERPROFILE", home)
    text = repo.uri(f"{home}/proj", "HEAD", "a.py")
    assert text == "git://~/proj#HEAD:a.py"
    assert repo.split_uri(text) == (f"{home}/proj", "HEAD", "a.py")
    assert repo.uri(f"{home}x/proj", "HEAD") == f"git://{home}x/proj#HEAD:"


def test_a_windows_path_gets_forward_slashes():
    assert repo.uri("C:\\proj", "HEAD", "a") == "git://C:/proj#HEAD:a"


@pytest.mark.parametrize("text", ["git:///proj", "git:///proj#HEAD", "file:///x", "git://#HEAD:a"])
def test_not_a_revision_uri(text):
    assert repo.split_uri(text) is None
