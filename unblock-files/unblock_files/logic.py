"""Plain functions with no XeFM in them — what the tests exercise.

Windows keeps the Mark of the Web in an NTFS alternate data stream named
``Zone.Identifier``, opened as ``<file>:Zone.Identifier``. It is a short INI
text, usually::

    [ZoneTransfer]
    ZoneId=3
    ReferrerUrl=https://example.com/downloads
    HostUrl=https://example.com/files/setup.exe

On another file system (FAT, exFAT, most network shares) the stream cannot
exist, and opening it simply fails as "not found".
"""

import codecs
import os
import urllib.parse
from dataclasses import dataclass

STREAM = "Zone.Identifier"

#: ZoneId → what Windows calls the zone.
ZONES = {0: "This computer", 1: "Local intranet", 2: "Trusted sites",
         3: "Internet", 4: "Restricted sites"}


@dataclass
class Mark:
    zone: int | None = None
    host_url: str = ""
    referrer_url: str = ""

    @property
    def zone_name(self):
        return ZONES.get(self.zone, "unknown zone" if self.zone is None
                         else f"zone {self.zone}")

    @property
    def source(self):
        """Where the file came from, as briefly as possible: the host of
        HostUrl, else of ReferrerUrl, else the zone's name."""
        for url in (self.host_url, self.referrer_url):
            host = urllib.parse.urlsplit(url).hostname if url else None
            if host:
                return host
        return self.zone_name


#: Windows error for a name with a stream on a volume that has no streams
#: (FAT, exFAT, some network shares): "The filename, directory name, or
#: volume label syntax is incorrect."
_ERROR_INVALID_NAME = 123


def stream_path(path):
    return f"{path}:{STREAM}"


def _no_stream(exc):
    return (isinstance(exc, (FileNotFoundError, NotADirectoryError))
            or getattr(exc, "winerror", None) == _ERROR_INVALID_NAME)


def decode(data):
    """The stream's text. Windows writes it in ANSI/UTF-8; some tools write
    UTF-16 with a BOM."""
    for bom, encoding in ((codecs.BOM_UTF16_LE, "utf-16"),
                          (codecs.BOM_UTF16_BE, "utf-16"),
                          (codecs.BOM_UTF8, "utf-8-sig")):
        if data.startswith(bom):
            return data.decode(encoding, errors="replace")
    return data.decode("utf-8", errors="replace")


def parse_mark(text):
    """A :class:`Mark` from the stream's text. Keys are matched without
    regard to case; sections other than [ZoneTransfer] are ignored."""
    mark = Mark()
    section = None
    for raw in text.splitlines():
        line = raw.strip().strip("\0")
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section != "zonetransfer" or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().lower(), value.strip()
        if key == "zoneid":
            try:
                mark.zone = int(value)
            except ValueError:
                pass
        elif key == "hosturl":
            mark.host_url = value
        elif key == "referrerurl":
            mark.referrer_url = value
    return mark


def read_mark(path):
    """The file's Mark of the Web, or ``None`` when it has none."""
    try:
        with open(stream_path(path), "rb") as stream:
            return parse_mark(decode(stream.read(64 * 1024)))
    except OSError as exc:
        if _no_stream(exc):
            return None
        raise


def remove_mark(path):
    """Delete the ``Zone.Identifier`` stream; the file itself is untouched.
    True when there was one to remove."""
    try:
        os.remove(stream_path(path))
        return True
    except OSError as exc:
        if _no_stream(exc):
            return False
        raise


def is_local(path_text):
    """XeFM prints a local path as a plain path and anything else (an archive,
    SSH, S3) as a URI; only a local file can carry the stream."""
    return "://" not in path_text


def confirm_prompt(marked):
    """One short line for the confirm dialog, which does not wrap: how many
    files and where they came from."""
    sources = []
    for _, mark in marked:
        if mark.source not in sources:
            sources.append(mark.source)
    shown = ", ".join(sources[:3]) + (f" and {len(sources) - 3} more"
                                      if len(sources) > 3 else "")
    n = len(marked)
    return f"Unblock {n} file{'s' if n != 1 else ''} downloaded from {shown}?"


def result_markdown(unblocked, unmarked, failed, *, md_escape):
    parts = []
    if unblocked:
        lines = [f"- {md_escape(name)} — {md_escape(mark.source)}"
                 + (f" ({md_escape(mark.host_url)})" if mark.host_url else "")
                 for name, mark in unblocked]
        parts.append(f"**Unblocked** ({len(unblocked)}) — Windows no longer "
                     "warns before opening these.\n\n" + "\n".join(lines))
    if unmarked:
        parts.append(f"{unmarked} file{'s' if unmarked != 1 else ''} had no mark.")
    if failed:
        parts.append("**Could not unblock**\n\n" + "\n".join(
            f"- {md_escape(name)}: {md_escape(reason)}" for name, reason in failed))
    return "\n\n".join(parts) or "Nothing to do."


def error_text(exc):
    return getattr(exc, "strerror", None) or str(exc) or type(exc).__name__
