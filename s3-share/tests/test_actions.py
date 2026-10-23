"""The action against a fake ctx shaped like xefm.user_api's. Needs XeFM
importable. AWS is never called: the work function is not run here (it is
presign_all's job, tested in test_logic.py)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from s3_share import actions  # noqa: E402


def entry(uri, is_dir=False):
    return SimpleNamespace(name=uri.rsplit("/", 1)[-1] or uri, path=uri, is_dir=is_dir)


class FakeCtx:
    def __init__(self, selected=(), focused=None):
        self.pane = SimpleNamespace(selected=lambda: list(selected), focused=focused)
        self.messages, self.copied, self.shown, self.choices = [], [], [], []

    def message(self, text):
        self.messages.append(text)

    def choose(self, title, items, *, type="choice", on_result=None):
        self.choices.append(list(items))
        self.on_result = on_result

    def run_task(self, title, work, *, on_done=None, read_only=False):
        assert read_only
        self.on_done = on_done

    def copy_text(self, text):
        self.copied.append(text)

    def show_markdown(self, title, source):
        self.shown.append(source)


@pytest.fixture(autouse=True)
def store(monkeypatch):
    state = {}
    ext = SimpleNamespace(state=SimpleNamespace(get=lambda k, d=None: state.get(k, d),
                                                set=state.__setitem__))
    monkeypatch.setattr(actions, "extension",
                        lambda name: ext if name.startswith("s3_share") else None)
    return state


def test_local_file_is_refused():
    ctx = FakeCtx(focused=entry("/home/me/a.txt"))
    actions.presign(ctx)
    assert ctx.messages == ["Presigned URL: works on files in an s3:// folder"]
    assert not ctx.choices


def test_asks_for_lifetime_and_remembers_it(store):
    ctx = FakeCtx(focused=entry("s3://bkt/a.txt"))
    actions.presign(ctx)
    assert ctx.choices[0] == ["1 hour", "1 day", "7 days"]
    ctx.on_result(1)                    # answered after the action returned
    assert store["lifetime"] == 86400
    ctx2 = FakeCtx(focused=entry("s3://bkt/a.txt"))
    actions.presign(ctx2)
    assert ctx2.choices[0][0] == "1 day"


def test_result_is_copied_and_shown():
    ctx = FakeCtx(selected=[entry("s3://bkt/a.txt"), entry("/local/b.txt")])
    actions.presign(ctx)
    ctx.on_result(0)
    links = [("bkt", "a.txt", "https://bkt.s3/a.txt?sig")]
    ctx.on_done(ctx, SimpleNamespace(ok=True, status="done",
                                     value=(links, [], True)))
    assert ctx.copied == ["https://bkt.s3/a.txt?sig"]
    assert "temporary credentials" in ctx.shown[0]


def test_failure_is_logged():
    ctx = FakeCtx(focused=entry("s3://bkt/a.txt"))
    actions.presign(ctx)
    ctx.on_result(0)
    ctx.on_done(ctx, SimpleNamespace(ok=False, status="failed",
                                     error="Unable to locate credentials"))
    assert ctx.messages[-1] == "Presigned URL: could not sign — Unable to locate credentials"
    assert not ctx.copied
