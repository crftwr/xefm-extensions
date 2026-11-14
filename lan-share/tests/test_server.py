"""The server, asked over a real socket on the loopback address. The shared
paths are ``pathlib`` ones: the server uses only what XeFM's paths share with
them (``stat``, ``iterdir``, ``is_dir``, ``open('rb')``, ``/``)."""

import http.client
import io
import os
import time
import zipfile

import pytest

from lan_share import server as server_module
from lan_share.server import Item, Share, ShareServer

TOKEN = "AbCdEfGhIjKl"
BIG = bytes(range(256)) * 4000              # 1,024,000 bytes


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "root"
    docs = root / "docs"
    (docs / "sub dir").mkdir(parents=True)
    (docs / "empty").mkdir()
    (docs / "a.txt").write_bytes(b"alpha\n")
    (docs / "sub dir" / "b#1.txt").write_bytes(b"beta\n")
    (docs / ".secret").write_bytes(b"hidden\n")
    (root / "movie.mp4").write_bytes(BIG)
    (root / "outside.txt").write_bytes(b"not shared\n")
    try:
        os.symlink(root / "outside.txt", docs / "link.txt")
    except (OSError, NotImplementedError):
        pass                                    # Windows without the privilege
    return root


def _serve(items, **options):
    idle = options.pop("idle_seconds", 0)
    stopped = options.pop("on_idle_stop", None)
    running = ShareServer(Share(items, TOKEN, **options), "127.0.0.1",
                          idle_seconds=idle, on_idle_stop=stopped)
    running.start()
    return running


@pytest.fixture
def share(tree):
    running = _serve([Item("docs", tree / "docs", True),
                      Item("movie.mp4", tree / "movie.mp4", False)])
    yield running
    running.stop()


def get(running, target, headers=None, method="GET"):
    connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=10)
    try:
        connection.request(method, target, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


# --- the token --------------------------------------------------------------- #

def test_nothing_is_served_without_the_token(share):
    for target in ("/", "/f/0/docs/a.txt", "/wrong/", f"/{TOKEN[:-1]}x/",
                   "/favicon.ico"):
        status, _, body = get(share, target)
        assert status == 404, target
        assert b"alpha" not in body


def test_other_methods_are_refused(share):
    for method in ("POST", "PUT", "DELETE"):
        status, _, _ = get(share, f"/{TOKEN}/f/1/movie.mp4", method=method)
        assert status == 501, method


# --- pages ------------------------------------------------------------------- #

def test_the_index_lists_the_shared_items(share):
    status, headers, body = get(share, f"/{TOKEN}/")
    page = body.decode()
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Cache-Control"] == "no-store"
    assert f'href="/{TOKEN}/f/0/docs/"' in page
    assert f'href="/{TOKEN}/f/1/movie.mp4"' in page
    assert f'href="/{TOKEN}/f/1/movie.mp4?dl"' in page
    assert "1000.0 KB" in page
    assert f'href="/{TOKEN}/?zip"' in page
    assert "outside" not in page


def test_a_folder_page_lists_folders_first_and_hides_dot_files_and_links(share):
    status, _, body = get(share, f"/{TOKEN}/f/0/docs/")
    page = body.decode()
    assert status == 200
    assert page.index(">empty/<") < page.index(">sub dir/<") < page.index(">a.txt<")
    assert ".secret" not in page and "link.txt" not in page
    assert f'href="/{TOKEN}/f/0/docs/sub%20dir/"' in page


def test_a_nested_folder_and_its_file(share):
    status, _, body = get(share, f"/{TOKEN}/f/0/docs/sub%20dir/")
    assert status == 200 and "b#1.txt" in body.decode()
    assert f"/{TOKEN}/f/0/docs/sub%20dir/b%231.txt" in body.decode()
    status, headers, body = get(share, f"/{TOKEN}/f/0/docs/sub%20dir/b%231.txt")
    assert (status, body) == (200, b"beta\n")
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers["Content-Disposition"].startswith("inline;")


# --- what stays out ---------------------------------------------------------- #

def test_paths_out_of_the_folder_are_not_found(share):
    for below in ("../outside.txt", "..%2foutside.txt", "%2e%2e/outside.txt",
                  "sub%20dir/../../outside.txt", "missing.txt"):
        status, _, body = get(share, f"/{TOKEN}/f/0/docs/{below}")
        assert status == 404, below
        assert b"not shared" not in body


def test_hidden_files_and_links_are_not_served(share, tree):
    assert get(share, f"/{TOKEN}/f/0/docs/.secret")[0] == 404
    if (tree / "docs" / "link.txt").is_symlink():
        status, _, body = get(share, f"/{TOKEN}/f/0/docs/link.txt")
        assert status == 404 and b"not shared" not in body


def test_hidden_files_are_served_when_shared(tree):
    running = _serve([Item("docs", tree / "docs", True)], include_hidden=True)
    try:
        assert ".secret" in get(running, f"/{TOKEN}/f/0/docs/")[2].decode()
        assert get(running, f"/{TOKEN}/f/0/docs/.secret")[2] == b"hidden\n"
    finally:
        running.stop()


def test_a_file_item_has_nothing_below_it_and_indexes_are_checked(share):
    assert get(share, f"/{TOKEN}/f/1/movie.mp4/x")[0] == 404
    assert get(share, f"/{TOKEN}/f/2/other")[0] == 404


# --- files ------------------------------------------------------------------- #

def test_a_whole_file(share):
    status, headers, body = get(share, f"/{TOKEN}/f/1/movie.mp4")
    assert status == 200 and body == BIG
    assert headers["Content-Length"] == str(len(BIG))
    assert headers["Accept-Ranges"] == "bytes"
    assert headers["Content-Type"] == "video/mp4"


def test_download_flag_makes_it_an_attachment(share):
    _, headers, _ = get(share, f"/{TOKEN}/f/1/movie.mp4?dl")
    assert headers["Content-Disposition"].startswith('attachment; filename="movie.mp4"')


def test_head_sends_the_headers_only(share):
    status, headers, body = get(share, f"/{TOKEN}/f/1/movie.mp4", method="HEAD")
    assert status == 200 and body == b""
    assert headers["Content-Length"] == str(len(BIG))


def test_ranges(share):
    target = f"/{TOKEN}/f/1/movie.mp4"
    status, headers, body = get(share, target, {"Range": "bytes=1000-1999"})
    assert status == 206 and body == BIG[1000:2000]
    assert headers["Content-Range"] == f"bytes 1000-1999/{len(BIG)}"
    status, headers, body = get(share, target, {"Range": "bytes=-10"})
    assert status == 206 and body == BIG[-10:]
    status, headers, body = get(share, target, {"Range": f"bytes={len(BIG) - 5}-"})
    assert status == 206 and body == BIG[-5:]
    status, headers, _ = get(share, target, {"Range": f"bytes={len(BIG)}-"})
    assert status == 416
    assert headers["Content-Range"] == f"bytes */{len(BIG)}"


def test_several_requests_on_one_connection(share):
    connection = http.client.HTTPConnection("127.0.0.1", share.port, timeout=10)
    try:
        for _ in range(3):
            connection.request("GET", f"/{TOKEN}/f/0/docs/a.txt")
            response = connection.getresponse()
            assert response.read() == b"alpha\n"
        connection.request("GET", "/nope")
        response = connection.getresponse()
        assert response.status == 404
        response.read()
        connection.request("GET", f"/{TOKEN}/f/0/docs/a.txt")
        assert connection.getresponse().read() == b"alpha\n"
    finally:
        connection.close()


class _Unseekable(io.RawIOBase):
    def __init__(self, data):
        self._data = io.BytesIO(data)

    def readable(self):
        return True

    def seekable(self):
        return False

    def readinto(self, buffer):
        return self._data.readinto(buffer)


class _StreamOnlyPath:
    """A path whose files cannot seek, as some remote storage's cannot."""
    name = "stream.bin"

    def __init__(self, data):
        self._data = data

    def __str__(self):
        return "fake://host/stream.bin"

    def stat(self):
        return os.stat_result((0o100644, 0, 0, 1, 0, 0, len(self._data), 0, 0, 0))

    def open(self, mode):
        assert mode == "rb"
        return _Unseekable(self._data)


def test_a_stream_that_cannot_seek_is_sent_whole():
    running = _serve([Item("stream.bin", _StreamOnlyPath(b"0123456789"), False)])
    try:
        status, headers, body = get(running, f"/{TOKEN}/f/0/stream.bin",
                                    {"Range": "bytes=2-4"})
        assert (status, body) == (200, b"0123456789")
        assert "Accept-Ranges" not in headers
    finally:
        running.stop()


class _BrokenPath(_StreamOnlyPath):
    def open(self, mode):
        raise PermissionError("no")


def test_a_file_that_cannot_be_read_is_a_500_and_the_server_lives(tree):
    running = _serve([Item("stream.bin", _BrokenPath(b"x"), False),
                      Item("docs", tree / "docs", True)])
    try:
        assert get(running, f"/{TOKEN}/f/0/stream.bin")[0] == 500
        assert get(running, f"/{TOKEN}/f/1/docs/a.txt")[2] == b"alpha\n"
    finally:
        running.stop()


# --- ZIP --------------------------------------------------------------------- #

def _names(body):
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.testzip() is None
        return sorted(archive.namelist()), archive


def test_a_folder_as_zip(share):
    status, headers, body = get(share, f"/{TOKEN}/f/0/docs/?zip")
    assert status == 200
    assert headers["Content-Type"] == "application/zip"
    assert headers["Content-Disposition"].startswith('attachment; filename="docs.zip"')
    names, _ = _names(body)
    assert names == ["docs/", "docs/a.txt", "docs/empty/", "docs/sub dir/",
                     "docs/sub dir/b#1.txt"]
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.read("docs/sub dir/b#1.txt") == b"beta\n"


def test_a_nested_folder_as_zip(share):
    _, headers, body = get(share, f"/{TOKEN}/f/0/docs/sub%20dir/?zip")
    names, _ = _names(body)
    assert names == ["sub dir/", "sub dir/b#1.txt"]
    assert 'filename="sub dir.zip"' in headers["Content-Disposition"]


def test_everything_as_zip(share):
    status, _, body = get(share, f"/{TOKEN}/?zip")
    assert status == 200
    names, _ = _names(body)
    assert "movie.mp4" in names and "docs/a.txt" in names
    assert "docs/.secret" not in names and "docs/link.txt" not in names
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert archive.read("movie.mp4") == BIG


def test_write_zip_keeps_file_times(tree):
    stamp = time.mktime((2024, 5, 6, 7, 8, 10, 0, 0, -1))
    os.utime(tree / "docs" / "a.txt", (stamp, stamp))
    out = io.BytesIO()

    class Sink:                                 # no tell/seek, like a socket
        write = staticmethod(out.write)
        flush = staticmethod(out.flush)

    server_module.write_zip(Share([], TOKEN), Sink, [("docs", tree / "docs", True)])
    with zipfile.ZipFile(io.BytesIO(out.getvalue())) as archive:
        assert archive.getinfo("docs/a.txt").date_time == (2024, 5, 6, 7, 8, 10)


# --- stopping ---------------------------------------------------------------- #

def test_stop_refuses_new_connections_and_can_be_repeated(tree):
    running = _serve([Item("docs", tree / "docs", True)])
    assert get(running, f"/{TOKEN}/")[0] == 200
    assert running.running
    running.stop()
    running.stop()
    assert not running.running
    with pytest.raises(OSError):
        get(running, f"/{TOKEN}/")


class _ZerosPath(_StreamOnlyPath):
    """A gigabyte of zeros: more than any socket buffer takes at once."""
    SIZE = 1 << 30

    def __init__(self):
        super().__init__(b"")

    def stat(self):
        return os.stat_result((0o100644, 0, 0, 1, 0, 0, self.SIZE, 0, 0, 0))

    def open(self, mode):
        class Zeros(io.RawIOBase):
            def readable(self):
                return True

            def seekable(self):
                return False

            def readinto(self, buffer):
                buffer[:] = bytes(len(buffer))
                return len(buffer)
        return Zeros()


def test_stop_ends_a_download_in_flight_and_drops_idle_clients():
    running = _serve([Item("zeros.bin", _ZerosPath(), False)])
    connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=10)
    idle = http.client.HTTPConnection("127.0.0.1", running.port, timeout=10)
    try:
        connection.request("GET", f"/{TOKEN}/f/0/zeros.bin")
        response = connection.getresponse()
        assert response.read(10) == bytes(10)
        idle.connect()                          # a kept-alive, silent client
        running.stop()
        with pytest.raises((OSError, http.client.HTTPException)):
            idle.request("GET", f"/{TOKEN}/")
            idle.getresponse()
        received = 10
        try:
            while True:
                data = response.read(1 << 20)
                if not data:
                    break
                received += len(data)
        except (OSError, http.client.HTTPException):
            pass
        assert received < _ZerosPath.SIZE       # cut short, not completed
    finally:
        connection.close()
        idle.close()


def test_idle_timeout_stops_the_server(tree):
    stopped = []
    running = _serve([Item("docs", tree / "docs", True)], idle_seconds=0.4,
                     on_idle_stop=lambda: stopped.append(True))
    assert get(running, f"/{TOKEN}/")[0] == 200
    deadline = time.monotonic() + 5
    while running.running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not running.running
    while not stopped and time.monotonic() < deadline:
        time.sleep(0.05)                        # called once the loop has left
    assert stopped == [True]


def test_a_taken_port_raises(tree):
    first = _serve([Item("docs", tree / "docs", True)])
    try:
        second = ShareServer(Share([], TOKEN), "127.0.0.1", first.port)
        with pytest.raises(OSError):
            second.start()
    finally:
        first.stop()
