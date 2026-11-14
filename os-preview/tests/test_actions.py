"""The action against a fake ctx shaped like xefm.user_api's. Nothing is
started: the fake records what run_program was asked to run. Needs XeFM
importable (for xefm_python)."""

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from os_preview import actions, logic  # noqa: E402


def entry(name, path=None):
    return SimpleNamespace(name=name, path=path or f"/home/me/{name}")


class FakeCtx:
    def __init__(self, selected=(), focused=None):
        self.pane = SimpleNamespace(selected=lambda: list(selected),
                                    focused=focused)
        self.messages, self.runs = [], []

    def message(self, text):
        self.messages.append(text)

    def run_program(self, command, *, terminal=False, cwd=None, env=None):
        self.runs.append((command, terminal, env))


@pytest.fixture
def macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(actions, "xefm_python", "/py")


def test_selection_goes_to_the_helper(macos):
    ctx = FakeCtx(selected=[entry("a.mov"), entry("b.mp3")],
                  focused=entry("other.txt"))
    actions.show(ctx)
    (command, terminal, env), = ctx.runs
    assert command == ["/py", logic.QUICKLOOK_HELPER,
                       "/home/me/a.mov", "/home/me/b.mp3"]
    assert terminal is False
    assert set(env) <= {"PYTHONPATH"}
    assert ctx.messages == []


def test_cursor_entry_when_nothing_is_selected(macos):
    ctx = FakeCtx(focused=entry("clip.mov"))
    actions.show(ctx)
    assert ctx.runs[0][0][2:] == ["/home/me/clip.mov"]


def test_remote_entries_are_left_out_and_said_so(macos):
    ctx = FakeCtx(selected=[entry("a.mov"),
                            entry("b.mov", "ssh://host/b.mov")])
    actions.show(ctx)
    assert ctx.runs[0][0][2:] == ["/home/me/a.mov"]
    assert ctx.messages == ["Quick Look: left out 1 item(s) not on the local disk"]


def test_only_remote_entries_starts_nothing(macos):
    ctx = FakeCtx(focused=entry("b.mov", "s3://bucket/b.mov"))
    actions.show(ctx)
    assert ctx.runs == []
    assert ctx.messages == ["Quick Look: only files on the local disk can be shown"]


def test_parent_row_and_empty_pane_start_nothing(macos):
    for focused in (entry("..", "/home"), None):
        ctx = FakeCtx(focused=focused)
        actions.show(ctx)
        assert ctx.runs == []
        assert ctx.messages == ["Quick Look: nothing to show"]


def test_a_platform_without_a_preview_says_so(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    ctx = FakeCtx(focused=entry("a.mov"))
    actions.show(ctx)
    assert ctx.runs == []
    assert ctx.messages == ["OS Preview: not available on this system"]
