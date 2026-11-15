"""Receiving: files sent to a share with an upload folder, over a real socket
on the loopback address, and the name rules behind it."""

import http.client
import json
import os
import socket
import threading
import time
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from lan_share import logic, server as server_module
from lan_share.server import Item, Share, ShareServer

TOKEN = "AbCdEfGhIjKl"


@pytest.fixture
def inbox(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "photo.jpg").write_bytes(b"already here")
    return folder


@pytest.fixture
def receiving(inbox):
    running = ShareServer(Share([], TOKEN, title="Send files", upload_dir=inbox),
                          "127.0.0.1")
    running.start()
    yield running
    running.stop()


def post(running, name, data, *, mtime=None, headers=None):
    target = f"/{TOKEN}/upload?name={quote(name, safe='')}"
    if mtime is not None:
        target += f"&mtime={mtime}"
    connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=10)
    try:
        connection.request("POST", target, body=data, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def saved_as(body):
    return json.loads(body)["name"]


def leftovers(folder):
    return [p.name for p in folder.iterdir() if p.name.startswith(".xefm-upload-")]


# --- the page ---------------------------------------------------------------- #

def test_the_page_offers_to_send(receiving):
    connection = http.client.HTTPConnection("127.0.0.1", receiving.port, timeout=10)
    connection.request("GET", f"/{TOKEN}/")
    page = connection.getresponse().read().decode()
    connection.close()
    assert 'type="file" multiple' in page
    assert "saved in <b>inbox</b>" in page
    assert "Nothing here." not in page
    assert "<ul>" not in page                   # no download list: nothing shared
    assert "Received with XeFM." in page


# --- saving ------------------------------------------------------------------ #

def test_a_file_is_saved_with_its_time(receiving, inbox):
    stamp = int(time.mktime((2025, 7, 1, 9, 30, 0, 0, 0, -1)) * 1000)
    status, body = post(receiving, "IMG_0042.HEIC", b"\x00heic" * 1000, mtime=stamp)
    assert status == 201
    assert json.loads(body) == {"name": "IMG_0042.HEIC", "size": 5000}
    saved = inbox / "IMG_0042.HEIC"
    assert saved.read_bytes() == b"\x00heic" * 1000
    assert saved.stat().st_mtime == pytest.approx(stamp / 1000)
    assert receiving.share.received_files() == [("IMG_0042.HEIC", 5000)]
    assert leftovers(inbox) == []


def test_an_empty_file(receiving, inbox):
    status, body = post(receiving, "empty.txt", b"")
    assert status == 201 and (inbox / "empty.txt").read_bytes() == b""


def test_a_name_taken_gets_a_number_and_nothing_is_replaced(receiving, inbox):
    assert saved_as(post(receiving, "photo.jpg", b"one")[1]) == "photo (1).jpg"
    assert saved_as(post(receiving, "photo.jpg", b"two")[1]) == "photo (2).jpg"
    assert (inbox / "photo.jpg").read_bytes() == b"already here"
    assert (inbox / "photo (1).jpg").read_bytes() == b"one"
    assert (inbox / "photo (2).jpg").read_bytes() == b"two"


def test_a_name_cannot_leave_the_folder_or_hide(receiving, inbox):
    assert saved_as(post(receiving, "../../escape.txt", b"x")[1]) == "escape.txt"
    assert saved_as(post(receiving, "..\\..\\win.txt", b"x")[1]) == "win.txt"
    assert saved_as(post(receiving, ".zshrc", b"x")[1]) == "_zshrc"
    assert (inbox / "escape.txt").exists() and (inbox / "_zshrc").exists()
    assert not (inbox.parent / "escape.txt").exists()
    assert not (inbox / ".zshrc").exists()


def test_a_name_with_nothing_left_is_refused(receiving, inbox):
    for name in ("", "..", "/", "...", "   "):
        status, body = post(receiving, name, b"x")
        assert status == 400, name
        assert b"no usable name" in body
    assert sorted(p.name for p in inbox.iterdir()) == ["photo.jpg"]


def test_without_a_size_it_is_refused(receiving, inbox):
    with socket.create_connection(("127.0.0.1", receiving.port), timeout=10) as sock:
        sock.sendall(f"POST /{TOKEN}/upload?name=a.txt HTTP/1.1\r\n"
                     f"Host: x\r\nTransfer-Encoding: chunked\r\n\r\n".encode())
        reply = sock.recv(4096)
    assert reply.startswith(b"HTTP/1.1 411")
    assert not (inbox / "a.txt").exists()


def test_not_enough_space(receiving, inbox, monkeypatch):
    monkeypatch.setattr(server_module.shutil, "disk_usage",
                        lambda path: SimpleNamespace(free=10))
    status, body = post(receiving, "big.bin", b"x" * 100)
    assert status == 507 and b"not enough space" in body
    assert not (inbox / "big.bin").exists() and leftovers(inbox) == []


def test_a_sender_that_goes_away_leaves_nothing(receiving, inbox):
    with socket.create_connection(("127.0.0.1", receiving.port), timeout=10) as sock:
        sock.sendall(f"POST /{TOKEN}/upload?name=cut.bin HTTP/1.1\r\nHost: x\r\n"
                     f"Content-Length: 100000\r\n\r\n".encode() + b"x" * 1000)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and leftovers(inbox):
        time.sleep(0.05)
    time.sleep(0.2)
    assert not (inbox / "cut.bin").exists()
    assert leftovers(inbox) == []
    assert receiving.share.received_files() == []


def test_the_folder_gone_is_a_refusal_not_a_crash(receiving, inbox):
    for path in inbox.iterdir():
        path.unlink()
    inbox.rmdir()
    status, body = post(receiving, "late.txt", b"x")
    assert status == 500
    assert post(receiving, "late.txt", b"x")[0] == 500     # still serving


def test_uploads_at_once_with_one_name_all_land(receiving, inbox):
    results = []

    def send(i):
        results.append(saved_as(post(receiving, "same.txt", f"{i}".encode())[1]))

    threads = [threading.Thread(target=send, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == sorted(
        ["same.txt"] + [f"same ({n}).txt" for n in range(1, 8)])
    contents = sorted((inbox / name).read_bytes() for name in results)
    assert contents == sorted(f"{i}".encode() for i in range(8))


def test_get_on_the_upload_path_is_not_found(receiving):
    connection = http.client.HTTPConnection("127.0.0.1", receiving.port, timeout=10)
    connection.request("GET", f"/{TOKEN}/upload?name=a")
    assert connection.getresponse().status == 404
    connection.close()


def test_without_the_token_nothing_is_saved(receiving, inbox):
    connection = http.client.HTTPConnection("127.0.0.1", receiving.port, timeout=10)
    connection.request("POST", "/wrong/upload?name=a.txt", body=b"x")
    assert connection.getresponse().status == 404
    connection.close()
    assert not (inbox / "a.txt").exists()


def test_a_share_can_give_and_take(tmp_path, inbox):
    (tmp_path / "give.txt").write_bytes(b"given")
    running = ShareServer(Share([Item("give.txt", tmp_path / "give.txt", False)],
                                TOKEN, upload_dir=inbox), "127.0.0.1")
    running.start()
    try:
        assert saved_as(post(running, "take.txt", b"taken")[1]) == "take.txt"
        connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=10)
        connection.request("GET", f"/{TOKEN}/f/0/give.txt")
        assert connection.getresponse().read() == b"given"
        connection.close()
    finally:
        running.stop()


# --- claiming a name --------------------------------------------------------- #

def test_claim_without_hard_links(tmp_path, monkeypatch):
    def no_links(src, dst):
        raise PermissionError("links not supported here")

    monkeypatch.setattr(server_module.os, "link", no_links)
    (tmp_path / "a.txt").write_bytes(b"old")
    part = tmp_path / ".xefm-upload-1.part"
    part.write_bytes(b"new")
    name = server_module.claim_name(part, tmp_path, "a.txt", threading.Lock())
    assert name == "a (1).txt"
    assert (tmp_path / "a.txt").read_bytes() == b"old"
    assert (tmp_path / "a (1).txt").read_bytes() == b"new"
    assert not part.exists()


def test_claim_counts_a_dangling_link_as_taken(tmp_path):
    try:
        os.symlink(tmp_path / "nowhere", tmp_path / "a.txt")
    except (OSError, NotImplementedError):
        pytest.skip("no symbolic links here")
    part = tmp_path / ".xefm-upload-2.part"
    part.write_bytes(b"new")
    assert server_module.claim_name(part, tmp_path, "a.txt", threading.Lock()) \
        == "a (1).txt"
    assert (tmp_path / "a.txt").is_symlink()


# --- the name rules ---------------------------------------------------------- #

@pytest.mark.parametrize("sent,saved", [
    ("IMG_0042.HEIC", "IMG_0042.HEIC"),
    ("写真.jpg", "写真.jpg"),
    ("a/b/c.txt", "c.txt"),
    ("C:\\Users\\me\\d.txt", "d.txt"),
    ('what?<is>|this*:"name".txt', "what__is__this___name_.txt"),
    ("tab\there.txt", "tab_here.txt"),
    (".bashrc", "_bashrc"),
    ("..hidden", "_.hidden"),
    ("trailing. . ", "trailing"),
    ("  spaced.txt  ", "spaced.txt"),
    ("CON", "_CON"),
    ("con.txt", "_con.txt"),
    ("lpt9.tar.gz", "_lpt9.tar.gz"),
    ("console.txt", "console.txt"),
    ("", None), ("..", None), (".", None), ("/", None), ("...", None),
])
def test_upload_name(sent, saved):
    assert logic.upload_name(sent) == saved


def test_upload_name_normalizes_to_nfc():
    # か + combining dakuten, as a Mac may send it, becomes が
    assert logic.upload_name("\u304b\u3099.txt") == "\u304c.txt"


def test_upload_name_keeps_within_255_bytes_and_the_extension():
    long = "あ" * 200 + ".jpeg"
    name = logic.upload_name(long)
    assert len(name.encode("utf-8")) <= 255
    assert name.endswith(".jpeg") and name.startswith("あ")
    plain = logic.upload_name("x" * 400)
    assert plain == "x" * 255


def test_candidate_names():
    names = logic.candidate_names("photo.jpg")
    assert [next(names) for _ in range(3)] == ["photo.jpg", "photo (1).jpg", "photo (2).jpg"]
    assert list(logic.candidate_names("a.tar.gz", limit=2)) == ["a.tar.gz", "a (1).tar.gz"]
    assert list(logic.candidate_names("v1.2.txt", limit=2)) == ["v1.2.txt", "v1.2 (1).txt"]
    assert list(logic.candidate_names("README", limit=2)) == ["README", "README (1)"]


def test_upload_mtime():
    assert logic.upload_mtime("1700000000123") == pytest.approx(1700000000.123)
    for value in (None, "", "abc", "0", "-5", str(2 ** 42)):
        assert logic.upload_mtime(value) is None, value


def test_upload_route_and_params():
    route = logic.parse_route(f"/{TOKEN}/upload?name=a%20b.jpg&mtime=12", TOKEN)
    assert route.kind == "upload"
    assert route.params == {"name": "a b.jpg", "mtime": "12"}
    assert logic.parse_route(f"/{TOKEN}/upload/x", TOKEN) is None
    assert logic.parse_route("/wrong/upload?name=a", TOKEN) is None
