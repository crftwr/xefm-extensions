"""The action against a fake ctx shaped like xefm.user_api's. Prompts and the
task are answered *after* the action returns, as XeFM does. Needs XeFM
importable."""

import io
from types import SimpleNamespace

import pytest
from PIL import Image

pytest.importorskip("xefm.user_api")

from images_to_pdf import actions  # noqa: E402


def png_bytes(color=(1, 2, 3)):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, "PNG")
    return buf.getvalue()


class FakePath:
    def __init__(self, data):
        self.data = data

    def open(self, mode):
        assert mode == "rb"
        return io.BytesIO(self.data)


def entry(name, data=b"", is_dir=False):
    stem, _, ext = name.rpartition(".")
    return SimpleNamespace(name=name, stem=stem or ext, suffix=f".{ext}" if stem else "",
                           is_dir=is_dir, path=FakePath(data))


class FakeJob:
    def checkpoint(self):
        pass

    def progress(self, done, total, *, detail=""):
        pass


class FakeCtx:
    def __init__(self, selected, dest):
        self.pane = SimpleNamespace(name="left", selected=lambda: list(selected),
                                    focused=selected[0] if selected else None)
        self.cds = []
        right = SimpleNamespace(name="right", path=dest,
                                cd=lambda p, focus_name=None: self.cds.append((p, focus_name)))
        self.other = self.right = right
        self.messages, self.shown, self.pending = [], [], []

    def message(self, text):
        self.messages.append(text)

    def input(self, prompt, default="", *, title="", on_accept=None, on_cancel=None):
        self.default = default
        self.pending.append(lambda answer: on_accept(answer if answer is not None else default))

    def confirm(self, prompt, *, title="Confirm", on_result=None):
        self.pending.append(on_result)

    def run_task(self, title, work, *, on_done=None, read_only=False):
        assert not read_only            # it writes a file
        self.pending.append(lambda _=None: on_done(
            self, SimpleNamespace(ok=True, status="done", value=work(FakeJob()))))

    def answer(self, value=None):
        self.pending.pop(0)(value)

    def show_markdown(self, title, source):
        self.shown.append((title, source))


def test_combines_into_the_other_pane(tmp_path):
    ctx = FakeCtx([entry("a.png", png_bytes()), entry("b.png", png_bytes((9, 9, 9)))],
                  tmp_path)
    actions.combine(ctx)
    assert ctx.default == "a.pdf"
    ctx.answer("album")                 # the name prompt
    assert not (tmp_path / "album.pdf").exists()    # the task has not run yet
    ctx.answer()                        # the task
    assert (tmp_path / "album.pdf").read_bytes().startswith(b"%PDF")
    assert ctx.cds == [(tmp_path, "album.pdf")]
    assert ctx.messages[-1].endswith("album.pdf — 2 page(s)")
    assert not ctx.shown


def test_non_images_are_skipped_and_listed(tmp_path):
    ctx = FakeCtx([entry("a.png", png_bytes()), entry("notes.txt", b"hello")], tmp_path)
    actions.combine(ctx)
    ctx.answer("")                      # accept the default name
    ctx.answer()
    assert (tmp_path / "a.pdf").exists()
    assert "notes.txt" in ctx.shown[0][1]


def test_existing_pdf_asks_before_replacing(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"keep me")
    ctx = FakeCtx([entry("a.png", png_bytes())], tmp_path)
    actions.combine(ctx)
    ctx.answer("")                      # name → asks to confirm
    ctx.answer(False)                   # no
    assert not ctx.pending
    assert (tmp_path / "a.pdf").read_bytes() == b"keep me"


def test_remote_destination_is_refused(tmp_path):
    ctx = FakeCtx([entry("a.png", png_bytes())], "ssh://host/home/me")
    actions.combine(ctx)
    assert not ctx.pending
    assert "local folder" in ctx.messages[0]


def test_bad_name_is_refused(tmp_path):
    ctx = FakeCtx([entry("a.png", png_bytes())], tmp_path)
    actions.combine(ctx)
    ctx.answer("sub/dir")
    assert not ctx.pending
    assert "not a file name" in ctx.messages[0]


def test_directories_alone_are_nothing(tmp_path):
    ctx = FakeCtx([entry("photos", is_dir=True)], tmp_path)
    actions.combine(ctx)
    assert ctx.messages == ["Images to PDF: no files selected"]
