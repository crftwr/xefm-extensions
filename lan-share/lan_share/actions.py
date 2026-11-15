"""The action lan-share contributes. It takes the action context ``ctx``; the
server is in server.py and the rest in plain functions (logic.py, qr.py), so
all of it can be tested without XeFM."""

import logging
import os
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path

from xefm.user_api import extension, md_code_block, md_escape

from lan_share import logic, qr
from lan_share.server import Item, Share, ShareServer

logger = logging.getLogger(__name__)

TITLE = "Share on Local Network"
RECEIVE_TITLE = "Receive on Local Network"
SHOWN_NAMES = 4
SHOWN_RECEIVED = 20

# The share that is up, if any. The dialog is modal, so a second one cannot
# normally start while it is open; this covers the ways around that.
_running = []


def share(ctx):
    """Share the selected files on the local network.

    Starts a small web server for the selected files and folders - or the one
    under the cursor when nothing is selected - and shows its link and a QR
    code. Any device on the same network opens the link in a browser: files
    download or play in place, folders are browsed or downloaded as ZIP.
    Nothing is installed on the other device, and nothing can be uploaded or
    changed. Files on ssh://, s3:// and inside archives are served straight
    from where they are. Sharing stops when the dialog is closed."""
    entries = ctx.pane.selected() or [ctx.pane.focused]
    items = [Item(e.name, e.path, bool(e.is_dir)) for e in entries
             if e is not None and e.name != ".."]
    if not items:
        ctx.message(f"{TITLE}: nothing to share")
        return
    settings = extension(__name__).settings
    _with_address(ctx, TITLE, settings,
                  lambda address: _begin(ctx, TITLE, items, address, settings))


def receive(ctx):
    """Receive files from the local network into this folder.

    Starts a small web server and shows its link and a QR code. Any device on
    the same network opens the link in a browser and sends files: a phone's
    photos, a document from a tablet. They are saved in the current pane's
    folder; a file never replaces one already there, it gets a new name like
    "photo (1).jpg". Nothing on this computer can be read through the link.
    Receiving stops when the dialog is closed."""
    where = ctx.pane.path
    folder = Path(str(where))
    if "://" in str(where) or not folder.is_absolute():
        ctx.message(f"{RECEIVE_TITLE}: files can only be received into a folder "
                    f"on this computer, not {where}")
        return
    if not folder.is_dir() or not os.access(folder, os.W_OK):
        ctx.message(f"{RECEIVE_TITLE}: cannot write to {folder}")
        return
    settings = extension(__name__).settings
    _with_address(ctx, RECEIVE_TITLE, settings,
                  lambda address: _begin(ctx, RECEIVE_TITLE, [], address, settings,
                                         upload_dir=folder))


def _with_address(ctx, title, settings, begin):
    """Work out the address the link uses, from the ``ADDRESS`` setting, and
    call ``begin(address)`` with it - at once, or after the user picked one."""
    wanted = str(settings.ADDRESS or "").strip()
    if not wanted:
        addresses = logic.usable_addresses(logic.default_route_address(), [])
        if not addresses:
            ctx.message(f"{title}: this machine has no network address to share on")
            return
        begin(addresses[0])
        return
    if wanted != "ask" and not wanted.endswith("."):
        begin(wanted)                           # a full address: bind says if not
        return
    addresses = logic.usable_addresses(logic.default_route_address(),
                                       logic.host_addresses())
    if not addresses:
        ctx.message(f"{title}: this machine has no network address to share on")
        return
    if wanted != "ask":
        address = logic.pick_configured(addresses, wanted)
        if address is None:
            ctx.message(f"{title}: no address here starts with {wanted} "
                        f"(found {', '.join(addresses)})")
            return
        begin(address)
        return
    if len(addresses) == 1:
        begin(addresses[0])
        return

    def chosen(index):
        if index is not None:
            begin(addresses[index])

    ctx.choose(f"{title}: Address", addresses, on_result=chosen)


def _begin(ctx, title, items, address, settings, upload_dir=None):
    for old in _running[:]:
        _stop(old)
    token = logic.new_token()
    idle_minutes = max(0, int(settings.IDLE_MINUTES))
    shared = Share(items, token, include_hidden=bool(settings.INCLUDE_HIDDEN),
                   title="Send files" if upload_dir is not None else "Shared files",
                   upload_dir=upload_dir)
    server = ShareServer(
        shared, address, int(settings.PORT), idle_seconds=idle_minutes * 60,
        on_idle_stop=lambda: logger.info(
            "%s: stopped after %d minutes without a request", title, idle_minutes))
    try:
        port = server.start()
    except (OSError, OverflowError) as exc:
        ctx.message(f"{title}: cannot listen on {address}: {exc}")
        return
    _running.append(server)
    url = logic.share_url(address, port, token)
    terminal = bool(ctx.is_terminal_backend)
    png = None
    try:
        modules = qr.encode(url.encode("ascii"))
    except (ValueError, UnicodeError):
        modules = None                          # the link alone still works
    if modules is None:
        code = ""
    elif terminal:
        light = str(settings.TERMINAL_QR).lower() != "dark"
        code = md_code_block("\n".join(qr.to_text(modules, light_ink=light)))
    else:
        png = write_png(qr.to_png(modules),
                        [tempfile.gettempdir(), extension(__name__).data_dir])
        code = f"![QR code]({png.as_posix()})" if png is not None else \
            "*(No QR code: the temporary folder's path has a space in it.)*"

    def closed():
        _stop(server)
        if png is not None:
            try:
                png.unlink()
            except OSError:
                pass
        if upload_dir is None:
            ctx.message(f"{title}: stopped")
            return
        # The log pane is where the names are told: the server runs on its
        # own thread, which may not use ctx, so it can only keep the list.
        received = shared.received_files()
        for name, size in received[:SHOWN_RECEIVED]:
            ctx.message(f"{title}: received {name} ({logic.format_size(size)})")
        if len(received) > SHOWN_RECEIVED:
            ctx.message(f"{title}: and {len(received) - SHOWN_RECEIVED} more")
        count = len(received)
        ctx.message(f"{title}: stopped, {count} "
                    f"{'file' if count == 1 else 'files'} received")

    over_ssh = terminal and bool(os.environ.get("SSH_CONNECTION"))
    remote_host = socket.gethostname() if over_ssh else None
    if upload_dir is None:
        source = dialog_markdown(
            url, code, [item.name + ("/" if item.is_dir else "") for item in items],
            idle_minutes=idle_minutes, remote_host=remote_host)
        what = f"sharing {len(items)} {'item' if len(items) == 1 else 'items'}"
    else:
        source = receive_markdown(url, code, str(upload_dir),
                                  idle_minutes=idle_minutes, remote_host=remote_host)
        what = f"receiving into {upload_dir}"
    ctx.show_markdown(title, source, on_close=closed)
    ctx.message(f"{title}: {what} at http://{address}:{port}/")


def running_servers():
    """The share that is up, as a list (empty or one). For the tests, and for
    anything that wants to know whether a share is running."""
    return list(_running)


def stop_all():
    """Stop every running share and wait until each has stopped."""
    for server in _running[:]:
        _running.remove(server)
        server.stop()


def _stop(server):
    if server in _running:
        _running.remove(server)
    # Off the UI thread: stopping waits for the server's loop to notice.
    threading.Thread(target=server.stop, name="lan-share-stop", daemon=True).start()


IMAGE_PREFIX = "xefm-lan-share-"
STALE_SECONDS = 24 * 60 * 60


def remove_stale_images(folder, now=None):
    """Remove QR images a share left behind - XeFM quit with the dialog still
    open - once they are a day old. A younger one may belong to a share
    another XeFM has open."""
    now = time.time() if now is None else now
    try:
        found = list(Path(folder).glob(f"{IMAGE_PREFIX}*.png"))
    except OSError:
        return
    for path in found:
        try:
            if now - path.stat().st_mtime >= STALE_SECONDS:
                path.unlink()
        except OSError:
            pass


def write_png(data, folders):
    """Write the QR image into the first of ``folders`` it can be shown from,
    and return its path; None when none will do. The dialog's Markdown names
    the file as ``![alt](path)``, which cannot carry a path with a space or a
    bracket in it."""
    for folder in folders:
        folder = Path(folder)
        if any(c.isspace() or c in "()" for c in folder.as_posix()):
            continue
        remove_stale_images(folder)
        path = folder / f"{IMAGE_PREFIX}{secrets.token_hex(6)}.png"
        try:
            path.write_bytes(data)
        except OSError:
            continue
        return path
    return None


def _stops_note(idle_minutes, verb):
    stops = f"{verb} stops when this dialog is closed (Esc or Enter)"
    if idle_minutes:
        stops += (f", or after {idle_minutes} "
                  f"{'minute' if idle_minutes == 1 else 'minutes'} without a request")
    return stops + "."


def _ssh_note(remote_host):
    return (f"XeFM is running on **{md_escape(remote_host)}** over SSH: the link "
            "is on that machine's network, which may not be the one this "
            "screen is on.")


def _assemble(intro, url, code, middle, notes):
    # The link before the code: in a short terminal the code fills the
    # dialog, and the link must not be the part scrolled out of sight. It is
    # also the first Copy button Tab reaches.
    parts = [intro, md_code_block(url)]
    if code:
        parts.append(code)
    parts.append(middle)
    parts.append("\n".join(f"- {note}" for note in notes))
    return "\n\n".join(parts)


def dialog_markdown(url, code, names, *, idle_minutes, remote_host=None):
    """The share dialog's Markdown: what to do, the link in a code block (its
    Copy button copies it), the QR code, what is shared, and what the reader
    should know before leaving it open."""
    shown = ", ".join(md_escape(name) for name in names[:SHOWN_NAMES])
    if len(names) > SHOWN_NAMES:
        shown += f" and {len(names) - SHOWN_NAMES} more"
    notes = [
        "Files download or play in the browser; folders can be browsed or "
        "downloaded as ZIP. Nothing can be uploaded or changed.",
        "Anyone on this network who has the link can download these files, "
        "and the connection is not encrypted. Do not share on a network you "
        "do not trust.",
        _stops_note(idle_minutes, "Sharing"),
    ]
    if remote_host:
        notes.insert(0, _ssh_note(remote_host))
    return _assemble("Open the link on any device on this network, or scan the "
                     "code with a phone.", url, code, f"**Sharing:** {shown}", notes)


def receive_markdown(url, code, folder, *, idle_minutes, remote_host=None):
    """The receive dialog's Markdown, in the share dialog's order: the link,
    the code, where files go, and what to know."""
    notes = [
        "A file never replaces one already here: it is saved under a new name, "
        "like photo (1).jpg. Nothing on this computer can be read through the "
        "link.",
        "Anyone on this network who has the link can send files here, and the "
        "connection is not encrypted. Do not receive on a network you do not "
        "trust.",
        _stops_note(idle_minutes, "Receiving"),
    ]
    if remote_host:
        notes.insert(0, _ssh_note(remote_host))
    return _assemble("Open the link on a phone or any device on this network, "
                     "or scan the code, and send files from there.", url, code,
                     f"**Saving into:** {md_escape(folder)}", notes)
