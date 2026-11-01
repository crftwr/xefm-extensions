import os
import subprocess

import pytest


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


@pytest.fixture
def work(tmp_path, monkeypatch):
    """A repository with two commits, then changes of every kind:
    ``src/app.py`` modified, ``src/old.py`` renamed to ``src/new.py`` and
    staged, ``README.md`` deleted, ``notes.txt`` untracked, ``docs/`` an
    untracked folder, ``lib/util.py`` unchanged."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = os.path.realpath(str(tmp_path / "proj"))
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Tester")
    git(root, "config", "user.email", "t@example.com")
    write(root, "src/app.py", "print('one')\n")
    write(root, "src/old.py", "x = 1\n")
    write(root, "lib/util.py", "def f(): pass\n")
    write(root, "README.md", "# proj\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "First")
    write(root, "src/app.py", "print('two')\n")
    git(root, "commit", "-q", "-am", "Second")
    git(root, "tag", "v1")
    write(root, "src/app.py", "print('three')\n")
    git(root, "mv", "src/old.py", "src/new.py")
    os.remove(os.path.join(root, "README.md"))
    write(root, "notes.txt", "todo\n")
    write(root, "docs/guide.md", "guide\n")
    return root
