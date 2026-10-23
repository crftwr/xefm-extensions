"""Plain functions with no XeFM in them — what the tests exercise."""

import io
import os

from PIL import Image, ImageOps

#: Page size is the image's own size at this resolution: one pixel, one point.
RESOLUTION = 72.0


def pdf_name(text, default):
    """The output file name from what the user typed: trimmed, ``.pdf`` added
    when missing, ``None`` when it is empty or not a plain file name."""
    name = (text or "").strip() or default
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


#: Suffixes that usually mean a picture, for choosing the default name only;
#: whether a file really is an image is decided by opening it.
IMAGE_SUFFIXES = frozenset(
    ".jpg .jpeg .png .gif .bmp .tif .tiff .webp .heic .heif .avif".split())


def default_name(entries):
    """``<stem>.pdf`` of the first entry that looks like a picture, so a
    selection that starts with ``notes.txt`` still suggests ``IMG_0001.pdf``.
    ``entries`` are ``(stem, suffix)`` pairs."""
    for stem, suffix in entries:
        if suffix.lower() in IMAGE_SUFFIXES:
            return f"{stem}.pdf"
    return f"{entries[0][0] if entries else 'images'}.pdf"


def folder_label(path):
    """A short name for the destination, for the prompt: its last part."""
    text = str(path)
    trimmed = text.rstrip("/\\")
    return trimmed.replace("\\", "/").rsplit("/", 1)[-1] or text


def is_local(path):
    """XeFM prints a local path as a plain path and anything else (an archive,
    SSH, S3) as a URI. The PDF is written with ``open()``, so only a local
    folder will do as the destination."""
    return "://" not in str(path)


def load_page(stream):
    """One image, ready to be a PDF page: decoded now (so the stream can be
    closed), turned upright by its EXIF orientation, and flattened to RGB —
    transparency onto white, since a PDF page has no alpha. Raises whatever
    Pillow raises for a file it cannot read."""
    data = stream.read()
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            im = im.convert("RGBA")
            page = Image.new("RGB", im.size, (255, 255, 255))
            page.paste(im, mask=im.getchannel("A"))
            return page
        if im.mode not in ("RGB", "L", "1"):
            im = im.convert("RGB")
        return im.copy()


def write_pdf(pages, target):
    """Write ``pages`` (Pillow images) to ``target`` as one PDF, through a
    temporary file next to it, so a failure never leaves half a PDF under
    the chosen name."""
    tmp = target.with_name(f".{target.name}.part")
    try:
        first, rest = pages[0], pages[1:]
        first.save(tmp, "PDF", save_all=True, append_images=rest,
                   resolution=RESOLUTION)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
