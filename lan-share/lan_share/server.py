"""The HTTP server behind a share. Standard library only, and nothing of
XeFM's except the path objects it is handed, which it reads the way a
``run_task`` worker may: ``stat``, ``iterdir``, ``open('rb')``.

One :class:`Share` holds what is offered; :class:`ShareServer` serves it on a
thread of its own until ``stop()``, or until nothing has asked for anything
for the idle time."""

import logging
import socket
import threading
import time
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lan_share import logic

logger = logging.getLogger(__name__)

CHUNK = 256 * 1024


class Item:
    """One shared entry: the name it is offered under, its path, and whether
    it is a folder — read from the pane before the server starts."""

    def __init__(self, name, path, is_dir):
        self.name, self.path, self.is_dir = name, path, is_dir


class Share:
    """What one share offers and how. ``items`` are :class:`Item`; ``title``
    heads the page."""

    def __init__(self, items, token, *, title="Shared files", include_hidden=False):
        self.items = list(items)
        self.token = token
        self.title = title
        self.include_hidden = include_hidden
        # Storage that is not the local disk (SSH, S3, an archive) is read by
        # one request at a time: this code cannot know how many readers such a
        # backend takes at once, and a browser opens several connections.
        self.remote_lock = threading.RLock()

    def lock_for(self, path):
        return self.remote_lock if "://" in str(path) else _NO_LOCK


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_NO_LOCK = _NoLock()


class _NotFound(Exception):
    pass


def _is_link(path):
    try:
        return bool(path.is_symlink())
    except (OSError, AttributeError, NotImplementedError):
        return False


def resolve(share, route):
    """The ``(item, path)`` a route names. Each step below a shared
    folder must be a plain name, visible under the share's hidden-files rule,
    and not a symbolic link — a link could lead out of what was shared. The
    shared items themselves may be links: the user picked those."""
    if not 0 <= route.index < len(share.items):
        raise _NotFound
    item = share.items[route.index]
    if route.segments and not item.is_dir:
        raise _NotFound
    path = item.path
    for segment in route.segments:
        if not logic.safe_segment(segment, include_hidden=share.include_hidden):
            raise _NotFound
        path = path / segment
        if _is_link(path):
            raise _NotFound
    return item, path


def list_folder(share, path):
    """``[(name, child, is_dir)]`` of a shared folder: folders first, then by
    name; links and (unless shared) hidden names left out."""
    rows = []
    for child in path.iterdir():
        name = child.name
        if not logic.safe_segment(name, include_hidden=share.include_hidden):
            continue
        if _is_link(child):
            continue
        rows.append((name, child, bool(child.is_dir())))
    rows.sort(key=lambda row: (not row[2], row[0].lower(), row[0]))
    return rows


def walk(share, path, prefix):
    """Every entry below a folder as ``(archive name, path, is_dir)``, a
    folder before what it holds. Iterative, so depth is no limit."""
    stack = [(path, prefix)]
    while stack:
        folder, arc = stack.pop()
        yield arc + "/", folder, True
        below = []
        for name, child, is_dir in list_folder(share, folder):
            if is_dir:
                below.append((child, f"{arc}/{name}"))
            else:
                yield f"{arc}/{name}", child, False
        stack.extend(reversed(below))


class _Writer:
    """What ``zipfile`` writes into: the socket, which cannot seek. Without
    ``tell``/``seek`` here, zipfile writes sizes after each file's data (data
    descriptors), which is what lets a ZIP be sent as it is built."""

    def __init__(self, wfile, on_write):
        self._wfile, self._on_write = wfile, on_write

    def write(self, data):
        self._wfile.write(data)
        self._on_write()
        return len(data)

    def flush(self):
        self._wfile.flush()


def _zip_time(path):
    try:
        stamp = time.localtime(path.stat().st_mtime)[:6]
    except (OSError, ValueError, OverflowError, AttributeError):
        return (1980, 1, 1, 0, 0, 0)
    return stamp if stamp[0] >= 1980 else (1980, 1, 1, 0, 0, 0)


def write_zip(share, out, roots, on_write=lambda: None):
    """Write a ZIP of ``roots`` (``[(archive name, path, is_dir)]``) to
    ``out`` as it is read. Stored, not compressed: what gets shared is mostly
    compressed already, and the network is local."""
    with zipfile.ZipFile(_Writer(out, on_write), "w", zipfile.ZIP_STORED,
                         allowZip64=True) as archive:
        for root_name, root_path, root_is_dir in roots:
            entries = walk(share, root_path, root_name) if root_is_dir \
                else [(root_name, root_path, False)]
            for arc, path, is_dir in entries:
                info = zipfile.ZipInfo(arc, date_time=_zip_time(path))
                if is_dir:
                    info.external_attr = (0o40755 << 16) | 0x10
                    archive.writestr(info, b"")
                    continue
                info.external_attr = 0o100644 << 16
                with path.open("rb") as source, \
                        archive.open(info, "w", force_zip64=True) as target:
                    while True:
                        data = source.read(CHUNK)
                        if not data:
                            break
                        target.write(data)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "XeFM"
    sys_version = ""
    timeout = 60                    # a stalled client gives its thread back

    # --- plumbing ----------------------------------------------------------- #

    def log_message(self, format, *args):       # noqa: A002 - the base's name
        # The base class writes to stderr, which in the terminal app is the
        # screen. XeFM routes `logging` into its own log instead.
        logger.debug("%s %s", self.address_string(), format % args)

    def do_GET(self):                           # noqa: N802 - the base's name
        self._serve(body=True)

    def do_HEAD(self):                          # noqa: N802
        self._serve(body=False)

    def _serve(self, body):
        share = self.server.share
        self.server.touch()
        self._headers_sent = False              # one handler, many requests
        route = logic.parse_route(self.path, share.token)
        try:
            if route is None:
                raise _NotFound
            if route.kind == "index":
                self._index(share, route, body)
            else:
                self._item(share, route, body)
        except _NotFound:
            self._plain(HTTPStatus.NOT_FOUND, "Not found", body)
        except (BrokenPipeError, ConnectionError, socket.timeout):
            self.close_connection = True        # the client went away
        except Exception as exc:                # a file that cannot be read
            logger.warning("lan-share: %s: %s: %s", self.path.split("?")[0][-60:],
                           exc.__class__.__name__, exc)
            if self._headers_sent:
                self.close_connection = True    # mid-body: cut it short
                self._abort()
            else:
                self._plain(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not read", body)
        finally:
            self.server.touch()

    _headers_sent = False

    def _begin(self, status, headers):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self._headers_sent = True

    def _abort(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _plain(self, status, text, body):
        data = (text + "\n").encode()
        self._headers_sent = False
        self._begin(status, {"Content-Type": "text/plain; charset=utf-8",
                             "Content-Length": str(len(data))})
        if body:
            self.wfile.write(data)

    def _html(self, text, body):
        data = text.encode("utf-8")
        self._begin(HTTPStatus.OK, {"Content-Type": "text/html; charset=utf-8",
                                    "Content-Length": str(len(data))})
        if body:
            self.wfile.write(data)

    # --- pages -------------------------------------------------------------- #

    def _index(self, share, route, body):
        token = share.token
        if route.zip:
            roots = [(item.name, item.path, item.is_dir) for item in share.items]
            self._zip(share, "shared.zip", roots, body)
            return
        rows = []
        for index, item in enumerate(share.items):
            href = logic.item_href(token, index, item.name, folder=item.is_dir)
            size = None
            if not item.is_dir:
                size = self._size(share, item.path)
            rows.append((item.name, href, item.is_dir, size,
                         href + ("?zip" if item.is_dir else "?dl")))
        zip_href = f"/{token}/?zip" if len(share.items) > 1 else None
        self._html(logic.render_page(share.title, [(share.title, None)], rows,
                                     zip_href=zip_href), body)

    def _size(self, share, path):
        try:
            with share.lock_for(path):
                return path.stat().st_size
        except Exception:                       # listed anyway, size unknown
            return None

    def _item(self, share, route, body):
        item, path = resolve(share, route)
        with share.lock_for(path):
            if route.segments:
                try:
                    is_dir = bool(path.is_dir())
                    exists = is_dir or bool(path.exists())
                except OSError:
                    exists = is_dir = False
                if not exists:
                    raise _NotFound
            else:
                is_dir = item.is_dir
            if not is_dir:
                self._file(share, path, route, body)
                return
            name = route.segments[-1] if route.segments else item.name
            if route.zip:
                self._zip(share, name + ".zip", [(name, path, True)], body)
                return
            self._folder(share, item, path, route, body)

    def _folder(self, share, item, path, route, body):
        token = share.token
        crumbs = [(share.title, f"/{token}/")]
        chain = [item.name, *route.segments]
        for depth, label in enumerate(chain):
            last = depth == len(chain) - 1
            crumbs.append((label, None if last else logic.item_href(
                token, route.index, item.name, chain[1:depth + 1], folder=True)))
        rows = []
        for name, child, is_dir in list_folder(share, path):
            below = [*route.segments, name]
            href = logic.item_href(token, route.index, item.name, below, folder=is_dir)
            size = None if is_dir else self._size(share, child)
            rows.append((name, href, is_dir, size,
                         href + ("?zip" if is_dir else "?dl")))
        here = logic.item_href(token, route.index, item.name, route.segments, folder=True)
        self._html(logic.render_page(
            f"{chain[-1]} - {share.title}", crumbs, rows,
            zip_href=here + "?zip", zip_label="Download this folder as ZIP"), body)

    # --- files -------------------------------------------------------------- #

    def _file(self, share, path, route, body):
        name = path.name
        size = path.stat().st_size
        with path.open("rb") as stream:
            try:
                seekable = bool(stream.seekable())
            except (AttributeError, OSError):
                seekable = False
            wanted = logic.parse_range(self.headers.get("Range"), size) \
                if seekable else None
            headers = {
                "Content-Type": logic.content_type(name),
                "Content-Disposition": logic.content_disposition(
                    name, attachment=route.download),
            }
            if seekable:
                headers["Accept-Ranges"] = "bytes"
            if wanted == "unsatisfiable":
                data = b"Range not satisfiable\n"
                self._begin(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, {
                    "Content-Type": "text/plain; charset=utf-8",
                    "Content-Range": f"bytes */{size}",
                    "Content-Length": str(len(data))})
                if body:
                    self.wfile.write(data)
                return
            if wanted is None:
                start, length, status = 0, size, HTTPStatus.OK
            else:
                start, end = wanted
                length, status = end - start + 1, HTTPStatus.PARTIAL_CONTENT
                headers["Content-Range"] = f"bytes {start}-{end}/{size}"
                stream.seek(start)
            headers["Content-Length"] = str(length)
            self._begin(status, headers)
            if not body:
                return
            left = length
            while left > 0:
                data = stream.read(min(CHUNK, left))
                if not data:
                    # Shorter than its size said (still being written, or the
                    # storage gave up): the length is promised, so end the
                    # connection rather than leave the client waiting.
                    self.close_connection = True
                    self._abort()
                    return
                self.wfile.write(data)
                left -= len(data)
                self.server.touch()

    def _zip(self, share, name, roots, body):
        # No Content-Length: the size is not known until the last file is
        # read. The end of the connection ends the body.
        self.close_connection = True
        self._begin(HTTPStatus.OK, {
            "Content-Type": "application/zip",
            "Content-Disposition": logic.content_disposition(name, attachment=True),
            "Connection": "close"})
        if not body:
            return
        remote = any("://" in str(path) for _, path, _ in roots)
        with (share.remote_lock if remote else _NO_LOCK):
            write_zip(share, self.wfile, roots, self.server.touch)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, share):
        super().__init__(address, _Handler)
        self.share = share
        self.last_activity = time.monotonic()
        self._clients = set()
        self._clients_lock = threading.Lock()

    def touch(self):
        self.last_activity = time.monotonic()

    def handle_error(self, request, client_address):
        # The base class prints a traceback to stderr - the screen, in the
        # terminal app. A dropped connection is the usual cause.
        logger.debug("lan-share: request from %s failed", client_address,
                     exc_info=True)

    def process_request(self, request, client_address):
        with self._clients_lock:
            self._clients.add(request)
        super().process_request(request, client_address)

    def shutdown_request(self, request):
        with self._clients_lock:
            self._clients.discard(request)
        super().shutdown_request(request)

    def drop_clients(self):
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class ShareServer:
    """A running share. ``start()`` binds and returns the port, or raises
    OSError; ``stop()`` ends it, and may be called from any thread, more than
    once. With ``idle_seconds`` it also ends by itself once nothing has been
    asked of it for that long; ``on_idle_stop`` is then called on the
    watching thread."""

    def __init__(self, share, address, port=0, *, idle_seconds=0, on_idle_stop=None):
        self.share = share
        self.address = address
        self.port = port
        self.idle_seconds = idle_seconds
        self.on_idle_stop = on_idle_stop
        self._server = None
        self._stopped = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self):
        return self._server is not None and not self._stopped.is_set()

    def start(self):
        self._server = _Server((self.address, self.port), self.share)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, name="lan-share",
                         kwargs={"poll_interval": 0.2}, daemon=True).start()
        if self.idle_seconds > 0:
            threading.Thread(target=self._watch_idle, name="lan-share-idle",
                             daemon=True).start()
        return self.port

    def _watch_idle(self):
        while not self._stopped.wait(min(5.0, self.idle_seconds / 4)):
            if time.monotonic() - self._server.last_activity >= self.idle_seconds:
                self.stop()
                if self.on_idle_stop is not None:
                    self.on_idle_stop()
                return

    def stop(self):
        with self._lock:
            if self._server is None or self._stopped.is_set():
                return
            self._stopped.set()
            server = self._server
        server.shutdown()               # returns once serve_forever has left
        server.drop_clients()           # downloads in flight end here
        server.server_close()
