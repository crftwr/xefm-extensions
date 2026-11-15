"""The parts of lan-share that need neither XeFM nor a socket: which address
to offer, what a request path means, which bytes a Range header asks for, and
the HTML of the page. Plain functions, so the tests can call them directly."""

import hmac
import html
import ipaddress
import mimetypes
import secrets
import socket
import unicodedata
from urllib.parse import parse_qs, quote, unquote, urlsplit


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
    shared items), ``"item"`` (``index`` into the shared items, then
    ``segments`` below it) or ``"upload"`` (a file sent to a receiving share);
    ``zip`` and ``download`` are the query flags, ``params`` every query
    value (the last one of each name)."""

    def __init__(self, kind, index=None, segments=(), *, zip=False, download=False,
                 params=None):
        self.kind = kind
        self.index = index
        self.segments = list(segments)
        self.zip = zip
        self.download = download
        self.params = dict(params or {})


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
    params = {name: values[-1] for name, values
              in parse_qs(parts.query, keep_blank_values=True).items()}
    options = {"zip": "zip" in params, "download": "dl" in params,
               "params": params}
    rest = [unquote(s) for s in segments[2:]]
    if rest and rest[-1] == "":
        rest.pop()                              # a trailing slash
    if not rest:
        return Route("index", **options)
    if rest == ["upload"]:
        return Route("upload", **options)
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


# --------------------------------------------------------------------------- #
# Uploads
# --------------------------------------------------------------------------- #

_NOT_IN_NAMES = set('<>:"/\\|?*')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
MAX_NAME_BYTES = 255


def upload_name(name):
    """The name a sent file is saved under, or None when nothing is left of
    it. What a browser sends is only a suggestion: any folder part goes, the
    characters Windows refuses (and control characters) become ``_``, and so
    does a leading dot - a sender must not be able to drop a ``.zshrc`` or a
    ``.git`` into the folder. Reserved Windows device names get a ``_`` in
    front, and the name is kept within 255 bytes, its extension intact. The
    rules are the same on every OS, so a file can move on unchanged."""
    name = unicodedata.normalize("NFC", str(name or ""))
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join("_" if ord(c) < 32 or ord(c) == 127 or c in _NOT_IN_NAMES else c
                   for c in name)
    name = name.strip().rstrip(". ")
    if not name or set(name) <= {"."}:
        return None
    if name.startswith("."):
        name = "_" + name[1:]
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    if stem.split(".")[0].upper() in _RESERVED:
        name = "_" + name
        stem = "_" + stem
    if len(name.encode("utf-8")) > MAX_NAME_BYTES:
        tail = (dot + suffix) if dot and len((dot + suffix).encode("utf-8")) <= 32 else ""
        room = MAX_NAME_BYTES - len(tail.encode("utf-8"))
        head = (stem if tail else name).encode("utf-8")[:room].decode("utf-8", "ignore")
        name = head.rstrip(". ") + tail
    return name


def candidate_names(name, limit=10000):
    """``name``, then ``stem (1).ext``, ``stem (2).ext`` ...: what to try
    until one is free. The number goes before the last extension, or before
    ``.tar.gz`` and the like."""
    yield name
    stem, dot, suffix = name.rpartition(".")
    if not dot or not stem:
        stem, dot, suffix = name, "", ""
    elif stem.lower().endswith(".tar") and len(stem) > 4:
        stem, suffix = stem[:-4], "tar." + suffix
    for n in range(1, limit):
        yield f"{stem} ({n}){dot}{suffix}"


def upload_mtime(value):
    """The file time a browser sent (``File.lastModified``, milliseconds), in
    seconds; None when it is missing or not plausible."""
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    if not 0 < millis < 2 ** 41:                # up to the year 2039 and well past
        return None
    return millis / 1000


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
label.pick {{ display: inline-block; border-radius: .5rem; padding: .7rem 1.2rem;
             background: #2a6fdb; color: #fff; font-weight: 600; cursor: pointer; }}
li progress {{ width: 6rem; }}
</style></head><body>
<h1>{heading}</h1>
{upload}{all}{listing}
<p class="note">{note}</p>
</body></html>
"""

# The upload half of a receiving share's page. Files go one at a time, each
# as the body of its own POST (no multipart to parse on the server), with the
# name and time in the query. Names are put on the page with textContent.
_UPLOAD = """<p>Files you send are saved in <b>{folder}</b> on the computer.
A file never replaces one already there: it gets a new name instead.</p>
<p><label class="pick">Choose files to send<input id="pick" type="file" multiple hidden></label></p>
<ul id="sent"></ul>
<script>
const pick = document.getElementById("pick"), sent = document.getElementById("sent");
pick.addEventListener("change", async () => {
  const files = Array.from(pick.files);
  pick.value = "";
  for (const file of files) await send(file);
});
function send(file) {
  return new Promise(done => {
    const row = document.createElement("li"), name = document.createElement("span");
    const bar = document.createElement("progress"), state = document.createElement("span");
    name.className = "name"; name.style.flex = "1"; name.style.opacity = "1";
    name.style.whiteSpace = "normal"; name.style.wordBreak = "break-all";
    name.textContent = file.name; bar.max = 1; bar.value = 0;
    row.append(name, bar, state); sent.prepend(row);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "upload?name=" + encodeURIComponent(file.name) +
             "&mtime=" + encodeURIComponent(file.lastModified || ""));
    xhr.upload.onprogress = e => { if (e.lengthComputable) bar.value = e.loaded / e.total; };
    xhr.onload = () => {
      bar.remove();
      if (xhr.status === 201) {
        const saved = JSON.parse(xhr.responseText).name;
        state.textContent = saved === file.name ? "Saved" : "Saved as " + saved;
      } else {
        state.textContent = "Not saved: " + xhr.responseText.trim();
      }
      done();
    };
    xhr.onerror = () => { bar.remove(); state.textContent = "Not saved: the connection was lost"; done(); };
    xhr.send(file);
  });
}
</script>
"""


def render_page(title, crumbs, rows, *, zip_href=None, zip_label="Download all as ZIP",
                upload_folder=None):
    """The HTML of one listing. ``crumbs`` is ``[(label, href or None)]``, the
    way down to this folder; ``rows`` is ``[(name, href, is_dir, size,
    get_href)]``, where ``get_href`` downloads the row (a folder as ZIP).
    ``upload_folder`` names the folder a receiving share saves into: the page
    then offers to send files, and lists nothing when there is nothing to
    download. Every name is escaped here: a file may be called anything."""
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
    upload = ""
    if upload_folder is not None:
        # replace, not format: the script is full of braces
        upload = _UPLOAD.replace("{folder}", html.escape(upload_folder))
    if not lines and upload_folder is None:
        lines.append("<li><span>Nothing here.</span></li>\n")
    listing = f"<ul>\n{''.join(lines)}</ul>" if lines else ""
    all_link = ""
    if zip_href:
        all_link = (f'<p class="all"><a class="get" href="'
                    f'{html.escape(zip_href, quote=True)}">'
                    f'{html.escape(zip_label)}</a></p>\n')
    note = ("Received with XeFM." if upload_folder is not None and not rows
            else "Shared with XeFM.") + " The link stops working when the share ends."
    return _PAGE.format(title=html.escape(title), heading=heading, upload=upload,
                        all=all_link, listing=listing, note=note)
