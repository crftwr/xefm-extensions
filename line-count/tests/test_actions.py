"""The action against a fake ctx shaped like xefm.user_api's. Needs XeFM
importable (for md_code_block / md_escape)."""

import io
from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from line_count import actions  # noqa: E402


class FakePath:
    def __init__(self, name, data=b"", children=None, error=None):
        self.name, self.data, self.children, self.error = name, data, children, error

    def is_dir(self):
        return self.children is not None

    def iterdir(self):
        return iter(self.children)

    def stat(self):
        return SimpleNamespace(st_size=len(self.data))

    def open(self, mode):
        assert mode == "rb"
        if self.error:
            raise self.error
        return io.BytesIO(self.data)


def entry(path):
    return SimpleNamespace(name=path.name, path=path, is_dir=path.is_dir())


class FakeJob:
    def __init__(self, cancel_after=None):
        self.n, self.cancel_after = 0, cancel_after

    def checkpoint(self):
        self.n += 1
        if self.cancel_after is not None and self.n > self.cancel_after:
            raise RuntimeError("cancelled")

    def cancelled(self):
        return False

    def progress(self, done, total, *, detail=""):
        pass

    def item_progress(self, done, total):
        pass


class FakeCtx:
    def __init__(self, selected=(), focused=None):
        self.pane = SimpleNamespace(selected=lambda: list(selected), focused=focused)
        self.messages, self.shown = [], []

    def message(self, text):
        self.messages.append(text)

    def run_task(self, title, work, *, on_done=None, read_only=False):
        assert read_only
        self.work, self.on_done = work, on_done   # XeFM runs it later

    def finish(self):
        value = self.work(FakeJob())
        self.on_done(self, SimpleNamespace(ok=True, status="done", value=value))

    def show_markdown(self, title, source):
        self.shown.append((title, source))


def test_counts_selection_including_a_folder():
    src = FakePath("src", children=[FakePath("a.py", b"x\ny\n"),
                                    FakePath("logo.png", b"\x89PNG\0\0")])
    notes = FakePath("notes.txt", b"one two three")
    ctx = FakeCtx(selected=[entry(src), entry(notes)])
    actions.count_lines(ctx)
    assert not ctx.shown            # nothing until the task runs
    ctx.finish()
    title, source = ctx.shown[0]
    assert title == "Count Lines"
    assert "3 lines  5 words" in source
    assert "src/a.py" in source and "notes.txt" in source
    assert "Skipped as binary" in source and "src/logo.png" in source


def test_falls_back_to_the_focused_file():
    f = FakePath("only.txt", b"hi\n")
    ctx = FakeCtx(focused=entry(f))
    actions.count_lines(ctx)
    ctx.finish()
    assert "only.txt" in ctx.shown[0][1]


def test_unreadable_file_is_listed():
    f = FakePath("locked.txt", error=PermissionError(13, "Permission denied"))
    ctx = FakeCtx(focused=entry(f))
    actions.count_lines(ctx)
    ctx.finish()
    assert "locked.txt: Permission denied" in ctx.shown[0][1]


def test_parent_entry_is_nothing_to_count():
    ctx = FakeCtx(focused=SimpleNamespace(name="..", path=None, is_dir=True))
    actions.count_lines(ctx)
    assert ctx.messages == ["Count Lines: nothing to count"]
