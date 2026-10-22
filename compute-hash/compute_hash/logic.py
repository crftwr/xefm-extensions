"""Plain functions with no XeFM in them — what the tests exercise."""

import hashlib

#: (label shown in the picker, hashlib name), in the picker's default order.
#: All are in hashlib's guaranteed set, so no dependency is needed.
ALGORITHMS = [
    ("MD5", "md5"),
    ("SHA-1", "sha1"),
    ("SHA-256", "sha256"),
    ("SHA-512", "sha512"),
    ("BLAKE2b", "blake2b"),
]

CHUNK_SIZE = 1024 * 1024


class Stopped(Exception):
    """Raised by :func:`digest_stream` when ``should_stop`` says so."""


def ordered_algorithms(last=None):
    """ALGORITHMS with the one named ``last`` (a hashlib name) moved to the
    front, so Enter in the picker repeats it. An unknown ``last`` changes
    nothing."""
    first = [a for a in ALGORITHMS if a[1] == last]
    return first + [a for a in ALGORITHMS if a[1] != last]


def digest_stream(stream, algorithm, should_stop=None, on_read=None):
    """The hex digest of everything readable from the binary ``stream``.

    ``should_stop`` is asked between chunks; when it returns true the read
    stops with :class:`Stopped`, so a large or remote file does not hold up a
    cancel. ``on_read`` is told the number of bytes read so far after each
    chunk."""
    h = hashlib.new(algorithm)
    read = 0
    while True:
        if should_stop is not None and should_stop():
            raise Stopped()
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            return h.hexdigest()
        h.update(chunk)
        read += len(chunk)
        if on_read is not None:
            on_read(read)


def progress_detail(name, read, size):
    """The progress dialog's line for a file being read: its name, and how
    far into it, when its size is known."""
    if not size:
        return name
    return f"{name} — {min(100, read * 100 // size)}%"


def checksum_line(digest, name):
    """One line in the form ``sha256sum`` (and ``md5sum``, ``b2sum``, …)
    prints and ``-c`` reads back: digest, two spaces, name.

    A name holding a backslash, newline or carriage return is escaped the
    way GNU coreutils does it, with a leading backslash marking the line."""
    if any(c in name for c in "\\\n\r"):
        name = (name.replace("\\", "\\\\").replace("\n", "\\n")
                .replace("\r", "\\r"))
        return f"\\{digest}  {name}"
    return f"{digest}  {name}"


def error_text(exc):
    """A one-line reason for a file that could not be read."""
    if isinstance(exc, OSError) and exc.strerror:
        return exc.strerror
    return str(exc) or type(exc).__name__
