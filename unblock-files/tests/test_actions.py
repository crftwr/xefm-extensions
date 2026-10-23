"""The action against a fake ctx shaped like xefm.user_api's: tasks and the
confirm are answered after the action returns, as XeFM does. The stream is
simulated by a sibling file named ``<file>:Zone.Identifier`` off Windows.
Needs XeFM importable."""

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from unblock_files import actions  # noqa: E402
from unblock_files.logic import STREAM, read_mark, stream_path  # noqa: E402

MARK = b"[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://dl.example.com/x\r\n"


def file(tmp_path, name, mark=True):
    f = tmp_path / name
    f.write_bytes(b"MZ")
    if mark:
        with open(stream_path(f), "wb") as s:
            s.write(MARK)
    return SimpleNamespace(name=name, path=f, is_dir=False)


class FakeJob:
    def checkpoint(self):
        pass

    def progress(self, done, total, *, detail=""):
        pass


class FakeCtx:
    def __init__(self, selected=(), focused=None):
        self.pane = SimpleNamespace(selected=lambda: list(selected), focused=focused)
        self.messages, self.shown, self.pending, self.prompts = [], [], [], []

    def message(self, text):
        self.messages.append(text)

    def run_task(self, title, work, *, on_done=None, read_only=False):
        self.pending.append(lambda _=None: on_done(
            self, SimpleNamespace(ok=True, status="done", value=work(FakeJob()))))

    def confirm(self, prompt, *, title="Confirm", on_result=None):
        self.prompts.append(prompt)
        self.pending.append(on_result)

    def answer(self, value=None):
        self.pending.pop(0)(value)

    def show_markdown(self, title, source):
        self.shown.append(source)


def test_scan_confirm_remove(tmp_path):
    a, b = file(tmp_path, "a.exe"), file(tmp_path, "b.txt", mark=False)
    ctx = FakeCtx(selected=[a, b])
    actions.unblock(ctx)
    ctx.answer()                        # the scan
    assert ctx.prompts[0] == "Unblock 1 file downloaded from dl.example.com?"
    assert read_mark(a.path) is not None    # nothing removed before the yes
    ctx.answer(True)                    # the confirm
    ctx.answer()                        # the removal
    assert read_mark(a.path) is None
    assert ctx.messages[-1] == "Unblock Files: unblocked 1 file(s)"
    assert "a.exe" in ctx.shown[0] and "1 file had no mark." in ctx.shown[0]


def test_declining_changes_nothing(tmp_path):
    a = file(tmp_path, "a.exe")
    ctx = FakeCtx(focused=a)
    actions.unblock(ctx)
    ctx.answer()
    ctx.answer(False)
    assert not ctx.pending
    assert read_mark(a.path) is not None


def test_nothing_marked(tmp_path):
    ctx = FakeCtx(focused=file(tmp_path, "plain.txt", mark=False))
    actions.unblock(ctx)
    ctx.answer()
    assert not ctx.prompts
    assert ctx.messages == ["Unblock Files: none of the 1 file(s) is marked"]


def test_remote_and_folders_are_skipped():
    remote = SimpleNamespace(name="a.exe", path="ssh://host/a.exe", is_dir=False)
    folder = SimpleNamespace(name="dl", path="/tmp/dl", is_dir=True)
    ctx = FakeCtx(selected=[remote, folder])
    actions.unblock(ctx)
    assert ctx.messages == ["Unblock Files: no local files selected"]
    assert not ctx.pending
