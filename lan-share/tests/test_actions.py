"""The action against a fake ctx shaped like xefm.user_api's. Needs XeFM
importable (for md_code_block / md_escape). The server really starts, on the
loopback address, so the link in the dialog is fetched for real."""

import http.client
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from lan_share import actions, logic  # noqa: E402


def entry(path, name=None):
    path = Path(path)
    return SimpleNamespace(name=name or path.name, path=path, is_dir=path.is_dir())


class FakeCtx:
    def __init__(self, selected=(), focused=None, terminal=False):
        self.pane = SimpleNamespace(selected=lambda: list(selected), focused=focused)
        self.is_terminal_backend = terminal
        self.messages, self.shown, self.choices = [], [], []

    def message(self, text):
        self.messages.append(text)

    def show_markdown(self, title, source, *, on_close=None):
        self.shown.append((title, source, on_close))

    def choose(self, title, items, *, type="choice", on_result=None):
        self.choices.append((title, list(items), on_result))


def settings(**overrides):
    values = dict(ADDRESS="127.0.0.1", PORT=0, IDLE_MINUTES=30,
                  INCLUDE_HIDDEN=False, TERMINAL_QR="light")
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def handle(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    value = SimpleNamespace(settings=settings(), data_dir=data)
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(actions.tempfile, "gettempdir", lambda: str(temp))
    monkeypatch.setattr(actions, "extension",
                        lambda module: value if module.startswith("lan_share.") else None)
    yield value
    actions.stop_all()


@pytest.fixture
def files(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"alpha\n")
    (tmp_path / "pics").mkdir()
    (tmp_path / "pics" / "p.jpg").write_bytes(b"jpeg")
    return tmp_path


def url_of(source):
    return re.search(r"http://[0-9.]+:\d+/[A-Za-z0-9_-]+/", source).group(0)


def fetch(url):
    host, port, path = re.match(r"http://([0-9.]+):(\d+)(/.*)", url).groups()
    connection = http.client.HTTPConnection(host, int(port), timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _wait_stopped(server):
    deadline = time.monotonic() + 5
    while server.running and time.monotonic() < deadline:
        time.sleep(0.02)
    return not server.running


def test_shares_the_selection_and_stops_on_close(handle, files):
    ctx = FakeCtx(selected=[entry(files / "a.txt"), entry(files / "pics")])
    actions.share(ctx)
    [(title, source, on_close)] = ctx.shown
    assert title == actions.TITLE
    url = url_of(source)
    assert url.startswith("http://127.0.0.1:")
    assert f"```\n{url}\n```" in source        # in a code block: a Copy button
    assert source.index(url) < source.index("![QR code]")   # never scrolled away
    assert "a.txt, pics/" in source
    assert "30 minutes without a request" in source
    status, page = fetch(url)
    assert status == 200 and b"a.txt" in page and b"pics/" in page
    png = Path(re.search(r"!\[QR code\]\(([^)]+)\)", source).group(1))
    assert png.name.startswith(actions.IMAGE_PREFIX)
    assert png.read_bytes().startswith(b"\x89PNG")
    [server] = actions.running_servers()

    on_close()
    assert _wait_stopped(server)
    assert not png.exists()
    assert ctx.messages[-1] == f"{actions.TITLE}: stopped"
    with pytest.raises(OSError):
        fetch(url)


def test_the_focused_entry_when_nothing_is_selected(handle, files):
    ctx = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(ctx)
    status, body = fetch(url_of(ctx.shown[0][1]) + "f/0/a.txt")
    assert (status, body) == (200, b"alpha\n")


def test_nothing_to_share(handle, files):
    for ctx in (FakeCtx(), FakeCtx(focused=entry(files, name=".."))):
        actions.share(ctx)
        assert ctx.shown == []
        assert ctx.messages == [f"{actions.TITLE}: nothing to share"]


def test_the_terminal_gets_a_text_qr_code(handle, files):
    ctx = FakeCtx(focused=entry(files / "a.txt"), terminal=True)
    actions.share(ctx)
    source = ctx.shown[0][1]
    assert "![" not in source
    assert "█" in source and "▄" in source
    assert list(handle.data_dir.iterdir()) == []


def test_ssh_sessions_are_told_whose_network_it_is(handle, files, monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.9 5000 10.0.0.2 22")
    ctx = FakeCtx(focused=entry(files / "a.txt"), terminal=True)
    actions.share(ctx)
    assert "over SSH" in ctx.shown[0][1]
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.9 5000 10.0.0.2 22")
    ctx = FakeCtx(focused=entry(files / "a.txt"), terminal=False)
    actions.share(ctx)                          # the desktop app is local
    assert "over SSH" not in ctx.shown[0][1]


def test_a_second_share_stops_the_first(handle, files):
    first = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(first)
    [old] = actions.running_servers()
    second = FakeCtx(focused=entry(files / "pics"))
    actions.share(second)
    assert _wait_stopped(old)
    assert len(actions.running_servers()) == 1 and actions.running_servers()[0] is not old
    first.shown[0][2]()                         # closing the old dialog later
    assert actions.running_servers() and actions.running_servers()[0].running


def test_an_address_that_cannot_be_bound(handle, files):
    handle.settings.ADDRESS = "192.0.2.77"      # TEST-NET-1: not this machine
    ctx = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(ctx)
    assert ctx.shown == []
    assert ctx.messages[-1].startswith(f"{actions.TITLE}: cannot listen on 192.0.2.77:")


def test_ask_offers_the_addresses_after_the_action_returns(handle, files, monkeypatch):
    handle.settings.ADDRESS = "ask"
    monkeypatch.setattr(logic, "default_route_address", lambda: "127.0.0.1")
    monkeypatch.setattr(logic, "usable_addresses",
                        lambda default, others: ["10.0.0.2", "127.0.0.1"])
    ctx = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(ctx)
    [(title, items, on_result)] = ctx.choices
    assert items == ["10.0.0.2", "127.0.0.1"] and ctx.shown == []
    on_result(None)                             # cancelled
    assert ctx.shown == [] and actions.running_servers() == []
    on_result(1)
    assert url_of(ctx.shown[0][1]).startswith("http://127.0.0.1:")


def test_a_prefix_that_matches_nothing(handle, files, monkeypatch):
    handle.settings.ADDRESS = "172.16."
    monkeypatch.setattr(logic, "usable_addresses",
                        lambda default, others: ["10.0.0.2"])
    ctx = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(ctx)
    assert ctx.shown == []
    assert "no address here starts with 172.16. (found 10.0.0.2)" in ctx.messages[-1]


def test_no_network_at_all(handle, files, monkeypatch):
    handle.settings.ADDRESS = ""
    monkeypatch.setattr(logic, "default_route_address", lambda: None)
    ctx = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(ctx)
    assert ctx.shown == []
    assert "no network address" in ctx.messages[-1]


def test_idle_minutes_zero_says_only_the_dialog_stops_it(handle, files):
    handle.settings.IDLE_MINUTES = 0
    ctx = FakeCtx(focused=entry(files / "a.txt"))
    actions.share(ctx)
    assert "without a request" not in ctx.shown[0][1]
    assert actions.running_servers()[0].idle_seconds == 0


def test_write_png_skips_folders_markdown_cannot_name(tmp_path):
    spaced = tmp_path / "with space"
    spaced.mkdir()
    plain = tmp_path / "plain"
    plain.mkdir()
    path = actions.write_png(b"png", [spaced, tmp_path / "missing", plain])
    assert path.parent == plain and path.read_bytes() == b"png"
    assert actions.write_png(b"png", [spaced]) is None


def test_stale_images_are_removed_young_ones_kept(tmp_path):
    import os
    old = tmp_path / f"{actions.IMAGE_PREFIX}old.png"
    young = tmp_path / f"{actions.IMAGE_PREFIX}young.png"
    other = tmp_path / "other.png"
    for path in (old, young, other):
        path.write_bytes(b"png")
    now = time.time()
    os.utime(old, (now - actions.STALE_SECONDS - 5,) * 2)
    os.utime(other, (now - actions.STALE_SECONDS - 5,) * 2)
    actions.remove_stale_images(tmp_path, now=now)
    assert not old.exists() and young.exists() and other.exists()


def test_dialog_markdown_shortens_a_long_list_and_escapes_names():
    names = ["a_b*.txt", "2", "3", "4", "5", "6"]
    source = actions.dialog_markdown("http://10.0.0.2:1/t/", "", names, idle_minutes=1)
    assert r"a\_b\*.txt" in source
    assert "and 2 more" in source
    assert "after 1 minute without" in source
