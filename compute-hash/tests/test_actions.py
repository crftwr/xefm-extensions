"""The action against a fake ctx shaped like xefm.user_api's. Needs XeFM
importable (for md_code_block / md_escape)."""

import hashlib
import io
from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from compute_hash import actions  # noqa: E402


class FakePath:
    def __init__(self, data=None, error=None):
        self.data, self.error = data, error

    def stat(self):
        if self.error:
            raise self.error
        return SimpleNamespace(st_size=len(self.data))

    def open(self, mode):
        assert mode == "rb"
        if self.error:
            raise self.error
        return io.BytesIO(self.data)


def entry(name, data=b"", *, is_dir=False, error=None):
    return SimpleNamespace(name=name, is_dir=is_dir,
                           path=FakePath(data, error))


class FakeJob:
    def __init__(self):
        self.progress_calls = []

    def checkpoint(self):
        pass

    def cancelled(self):
        return False

    def progress(self, done, total, *, detail=""):
        self.progress_calls.append((done, total, detail))


class FakeCtx:
    def __init__(self, selected=(), focused=None, state=None, pick=None):
        self.pane = SimpleNamespace(selected=lambda: list(selected),
                                    focused=focused)
        store = dict(state or {})
        self.extension = SimpleNamespace(state=SimpleNamespace(
            get=lambda k, d=None: store.get(k, d),
            set=store.__setitem__))
        self.store = store
        self.pick = pick
        self.messages, self.shown, self.choices = [], [], []

    def message(self, text):
        self.messages.append(text)

    def choose(self, title, items, *, type="choice", on_result=None):
        self.choices.append((title, list(items), type))
        self.answer = lambda: on_result(self.pick(list(items)) if self.pick else None)

    def run_task(self, title, work, *, on_done=None, read_only=False):
        assert read_only
        self.job = FakeJob()
        value = work(self.job)
        on_done(self, SimpleNamespace(ok=True, status="done", value=value))

    def show_markdown(self, title, source):
        self.shown.append((title, source))


def run(ctx):
    """The action, then the user's answer to its prompt — which, as in XeFM,
    arrives after the action has returned and ctx.extension is gone."""
    actions.compute(ctx)
    ctx.extension = None
    if ctx.choices:
        ctx.answer()


def test_no_files_says_so():
    ctx = FakeCtx(focused=entry("..", is_dir=True))
    run(ctx)
    assert ctx.messages == ["Compute Hash: no files to hash"]
    assert ctx.choices == []


def test_cancelled_choice_does_nothing():
    ctx = FakeCtx(focused=entry("a.txt"))
    run(ctx)
    assert ctx.shown == [] and ctx.store == {}


def test_hashes_selection_in_order_and_skips_dirs():
    ctx = FakeCtx(selected=[entry("b.txt", b"b"), entry("dir", is_dir=True),
                            entry("a.txt", b"a")],
                  focused=entry("ignored"),
                  pick=lambda items: items.index("SHA-256"))
    run(ctx)
    (title, source), = ctx.shown
    assert title == "Compute Hash"
    assert ctx.choices[0][2] == "filter"
    assert ctx.store == {"algorithm": "sha256"}
    sha = lambda d: hashlib.sha256(d).hexdigest()  # noqa: E731
    assert f"{sha(b'b')}  b.txt\n{sha(b'a')}  a.txt" in source
    assert source.startswith("**SHA-256**")
    assert ctx.job.progress_calls[-1] == (2, 2, "")


def test_last_algorithm_is_offered_first():
    ctx = FakeCtx(focused=entry("a.txt", b"x"), state={"algorithm": "md5"},
                  pick=lambda items: 0)
    run(ctx)
    assert ctx.choices[0][1][0] == "MD5"
    assert hashlib.md5(b"x").hexdigest() in ctx.shown[0][1]


def test_unreadable_file_is_listed_apart():
    ctx = FakeCtx(selected=[entry("ok.txt", b"1"),
                            entry("no_*.txt", error=PermissionError(13, "Permission denied"))],
                  pick=lambda items: items.index("SHA-1"))
    run(ctx)
    source = ctx.shown[0][1]
    assert f"{hashlib.sha1(b'1').hexdigest()}  ok.txt" in source
    assert "**Could not read**\n\n- no\\_\\*.txt: Permission denied" in source
