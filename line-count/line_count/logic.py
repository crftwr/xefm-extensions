"""Plain functions with no XeFM in them — what the tests exercise."""

import codecs
from dataclasses import dataclass

#: How much is read at a time.
CHUNK = 1 << 20
#: A NUL byte in this much of the start of a file marks it as binary.
SNIFF = 8192
#: Rows shown in the result table; the totals always cover every file.
MAX_ROWS = 200


class Binary(Exception):
    """The file is not text."""


@dataclass
class Counts:
    lines: int = 0
    words: int = 0
    chars: int = 0

    def __iadd__(self, other):
        self.lines += other.lines
        self.words += other.words
        self.chars += other.chars
        return self


def count_stream(stream, cancelled=lambda: False, on_read=None):
    """Lines, words and characters of a binary ``stream``, read in chunks.

    - Lines are what an editor shows: a last line without a newline still
      counts (``wc -l`` would not count it).
    - Words are runs of non-whitespace (``str.split()``'s idea of
      whitespace, which includes Unicode spaces), as ``wc -w`` counts them.
    - Characters are counted after decoding as UTF-8; an invalid byte counts
      as one character (it would show as U+FFFD).

    Raises :class:`Binary` when the first block has a NUL byte. Stops early,
    returning what it has, when ``cancelled()`` turns true; the caller decides
    what that means. ``on_read(total_bytes)`` is called after each chunk."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    counts = Counts()
    last = ""
    read = 0
    first = True
    while True:
        if cancelled():
            break
        data = stream.read(CHUNK)
        if first:
            if b"\0" in data[:SNIFF]:
                raise Binary()
            if data.startswith(codecs.BOM_UTF8):
                data = data[len(codecs.BOM_UTF8):]
            first = False
        final = not data
        text = decoder.decode(data, final=final)
        if text:
            counts.chars += len(text)
            counts.lines += text.count("\n")
            counts.words += len(text.split())
            # A word split across two chunks was counted in both.
            if last and not last.isspace() and not text[0].isspace():
                counts.words -= 1
            last = text[-1]
        if final:
            break
        read += len(data)
        if on_read:
            on_read(read)
    if last and last != "\n":
        counts.lines += 1
    return counts


def walk(path, name, cancelled=lambda: False):
    """``(display name, path)`` for every file under ``path``, which is a file
    or a directory. Hidden entries (a leading ``.``) inside a directory are
    skipped; ``path`` itself is always taken, since it was chosen. Directories
    are listed in name order, so the result is stable."""
    if not path.is_dir():
        yield name, path
        return
    stack = [(path, name)]
    while stack:
        if cancelled():
            return
        folder, label = stack.pop()
        try:
            children = sorted(folder.iterdir(), key=lambda p: p.name.lower())
        except Exception:
            continue
        dirs = []
        for child in children:
            if child.name.startswith("."):
                continue
            child_label = f"{label}/{child.name}"
            try:
                is_dir = child.is_dir()
            except Exception:
                continue
            if is_dir:
                dirs.append((child, child_label))
            else:
                yield child_label, child
        stack.extend(reversed(dirs))


def fmt(n):
    return f"{n:,}"


def result_markdown(results, binary, failed, *, md_escape, md_code_block,
                    max_rows=MAX_ROWS):
    """The result dialog's Markdown. ``results`` is ``[(name, Counts)]``,
    ``binary`` names skipped as binary, ``failed`` ``[(name, reason)]``."""
    total = Counts()
    for _, counts in results:
        total += counts
    parts = []
    if results:
        rows = sorted(results, key=lambda r: (-r[1].lines, r[0].lower()))
        files = f"{len(results)} file" + ("" if len(results) == 1 else "s")
        parts.append(md_code_block(
            f"{fmt(total.lines)} lines  {fmt(total.words)} words  "
            f"{fmt(total.chars)} characters  ({files})"))
        table = ["| Lines | Words | Characters | File |",
                 "|---:|---:|---:|---|"]
        for name, c in rows[:max_rows]:
            table.append(f"| {fmt(c.lines)} | {fmt(c.words)} | {fmt(c.chars)} "
                         f"| {md_escape(name)} |")
        if len(results) > 1:
            table.append(f"| **{fmt(total.lines)}** | **{fmt(total.words)}** | "
                         f"**{fmt(total.chars)}** | **Total** |")
        parts.append("\n".join(table))
        if len(rows) > max_rows:
            parts.append(f"The {fmt(max_rows)} longest files are shown; "
                         f"the totals include all {fmt(len(rows))}.")
    else:
        parts.append("No text files to count.")
    if binary:
        parts.append(f"**Skipped as binary** ({len(binary)}): "
                     + ", ".join(md_escape(n) for n in binary[:50])
                     + (" …" if len(binary) > 50 else ""))
    if failed:
        parts.append("**Could not read**\n\n" + "\n".join(
            f"- {md_escape(name)}: {md_escape(reason)}" for name, reason in failed))
    return "\n\n".join(parts)


def error_text(exc):
    """A short reason for a file that could not be read."""
    text = getattr(exc, "strerror", None) or str(exc) or type(exc).__name__
    return text
