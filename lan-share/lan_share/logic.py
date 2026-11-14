"""The parts of lan-share that need neither XeFM nor a socket: which address
to offer, what a request path means, which bytes a Range header asks for, and
the HTML of the page. Plain functions, so the tests can call them directly."""

import hmac
import html
import ipaddress
import mimetypes
import secrets
import socket
from urllib.parse import quote, unquote, urlsplit


# --------------------------------------------------------------------------- #
# Addresses
# --------------------------------------------------------------------------- #

def default_route_address():
    """The address this machine uses to reach other networks, or None. A UDP
    socket is "connected" (nothing is sent) and asked which local address it
    got: the interface a phone on the same network would reach."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))          # TEST-NET-1: never routed to
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def host_addresses():
    """Every IPv4 address the host name resolves to; empty when it does not."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return [info[4][0] for info in infos]


def usable_addresses(default, others):
    """The addresses worth offering, the default route's first: no loopback,
    no link-local (169.254), no duplicates."""
    result = []
    for text in [default, *others]:
        if not text or text in result:
            continue
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            continue
        if address.version != 4 or address.is_loopback or address.is_link_local \
                or address.is_unspecified:
            continue
        result.append(text)
    return result


def pick_configured(addresses, wanted):
    """The address the ``ADDRESS`` setting names, when the machine has it.
    ``wanted`` is a full address or a prefix (``"192.168."``)."""
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    for address in addresses:
        if address == wanted or (wanted.endswith(".") and address.startswith(wanted)):
            return address
    return None


def new_token():
    """The secret part of the URL: 72 random bits, URL-safe."""
    return secrets.token_urlsafe(9)


def share_url(address, port, token):
    return f"http://{address}:{port}/{token}/"


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #

class Route:
    """What a request path asks for. ``kind`` is ``"index"`` (the page of the
    shared items) or ``"item"`` (``index`` into the shared items, then
    ``segments`` below it); ``zip`` and ``download`` are the query flags."""

    def __init__(self, kind, index=None, segments=(), *, zip=False, download=False):
        self.kind = kind
        self.index = index
        self.segments = list(segments)
        self.zip = zip
        self.download = download


def parse_route(target, token):
    """The :class:`Route` for a request target, or None for anything that is
    not under ``/<token>/`` — which is answered 404, the same as a wrong
    token, so the reply does not say whether a share exists."""
    parts = urlsplit(target)
    segments = parts.path.split("/")
    if len(segments) < 3 or segments[0] != "":
        return None
    given = unquote(segments[1])
    if not hmac.compare_digest(given.encode(), token.encode()):
        return None
    flags = {flag.split("=")[0] for flag in parts.query.split("&") if flag}
    options = {"zip": "zip" in flags, "download": "dl" in flags}
    rest = [unquote(s) for s in segments[2:]]
    if rest and rest[-1] == "":
        rest.pop()                              # a trailing slash
    if not rest:
        return Route("index", **options)
    # /<token>/f/<index>/<name>/<below>...: the name is there for the browser
    # (what it calls a saved file); the index is what selects the item.
    if rest[0] != "f" or len(rest) < 3 or not rest[1].isdigit():
        return None
    below = rest[3:]
    if not all(safe_segment(s) for s in below):
        return None
    return Route("item", int(rest[1]), below, **options)


def safe_segment(name, *, include_hidden=True):
    """Whether ``name`` may be one step below a shared folder: a plain name,
    never a way out of the folder."""
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\0" in name:
        return False
    return include_hidden or not name.startswith(".")


def parse_range(header, size):
    """The ``(start, end)`` bytes, inclusive, that a ``Range`` header asks for
    in a file of ``size`` bytes. None when there is no usable header (send the
    whole file), ``"unsatisfiable"`` when it lies outside the file (416).
    Several ranges in one header are answered with the whole file."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[len("bytes="):].strip()
    if "," in spec or "-" not in spec:
        return None
    first, _, last = spec.partition("-")
    first, last = first.strip(), last.strip()
    try:
        if first == "":
            if last == "":
                return None
            length = int(last)                  # the last N bytes
            if length <= 0:
                return "unsatisfiable"
            return (max(0, size - length), size - 1) if size else "unsatisfiable"
        start = int(first)
        end = int(last) if last else size - 1
    except ValueError:
        return None
    if start < 0 or start >= size:
        return "unsatisfiable"
    if end < start:
        return None
    return start, min(end, size - 1)


def content_type(name):
    kind, encoding = mimetypes.guess_type(name)
    if kind is None or encoding is not None:    # .gz and friends: as they are
        return "application/octet-stream"
    if kind.startswith("text/"):
        return f"{kind}; charset=utf-8"
    return kind


def content_disposition(name, *, attachment):
    """A Content-Disposition value that carries any file name: an ASCII
    fallback, then the real name as RFC 5987 ``filename*``."""
    fallback = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_"
                       for c in name)
    kind = "attachment" if attachment else "inline"
    return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


def item_href(token, index, name, below=(), *, folder=False):
    path = "/".join(quote(part, safe="") for part in [name, *below])
    return f"/{quote(token, safe='')}/f/{index}/{path}" + ("/" if folder else "")


def format_size(size):
    if size is None:
        return ""
    value = float(size)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            break
        value /= 1024
    return f"{int(value)} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 16px/1.4 system-ui, sans-serif; margin: 0 auto; max-width: 44rem;
       padding: 1rem; }}
h1 {{ font-size: 1.15rem; word-break: break-all; }}
ul {{ list-style: none; padding: 0; margin: 0; }}
li {{ display: flex; align-items: center; gap: .75rem; padding: .7rem 0;
     border-bottom: 1px solid rgba(128, 128, 128, .35); }}
li a.name {{ flex: 1; word-break: break-all; text-decoration: none; }}
li span {{ opacity: .65; font-size: .85rem; white-space: nowrap; }}
a.get {{ border: 1px solid currentColor; border-radius: .4rem;
        padding: .25rem .6rem; font-size: .85rem; text-decoration: none;
        white-space: nowrap; }}
p.all {{ margin: 1rem 0; }}
p.note {{ opacity: .65; font-size: .85rem; margin-top: 1.5rem; }}
</style></head><body>
<h1>{heading}</h1>
{all}<ul>
{rows}</ul>
<p class="note">Shared with XeFM. The link stops working when the share ends.</p>
</body></html>
"""


def render_page(title, crumbs, rows, *, zip_href=None, zip_label="Download all as ZIP"):
    """The HTML of one listing. ``crumbs`` is ``[(label, href or None)]``, the
    way down to this folder; ``rows`` is ``[(name, href, is_dir, size,
    get_href)]``, where ``get_href`` downloads the row (a folder as ZIP).
    Every name is escaped here: a file may be called anything."""
    heading = " / ".join(
        f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
        if href else html.escape(label)
        for label, href in crumbs)
    lines = []
    for name, href, is_dir, size, get_href in rows:
        label = html.escape(name) + ("/" if is_dir else "")
        detail = "folder" if is_dir else html.escape(format_size(size))
        get = "ZIP" if is_dir else "Download"
        lines.append(
            f'<li><a class="name" href="{html.escape(href, quote=True)}">{label}</a>'
            f'<span>{detail}</span>'
            f'<a class="get" href="{html.escape(get_href, quote=True)}">{get}</a></li>\n')
    if not lines:
        lines.append("<li><span>Nothing here.</span></li>\n")
    all_link = ""
    if zip_href:
        all_link = (f'<p class="all"><a class="get" href="'
                    f'{html.escape(zip_href, quote=True)}">'
                    f'{html.escape(zip_label)}</a></p>\n')
    return _PAGE.format(title=html.escape(title), heading=heading,
                        all=all_link, rows="".join(lines))
