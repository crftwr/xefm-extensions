import io
import re

import pytest
from PIL import Image

from images_to_pdf.logic import (
    default_name, folder_label, is_local, load_page, pdf_name, write_pdf)


def png(size=(40, 20), mode="RGB", color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, "PNG")
    return buf.getvalue()


def jpeg_rotated(size=(40, 20), orientation=6):
    """A landscape JPEG whose EXIF says 'rotate 90° to view'."""
    im = Image.new("RGB", size, (10, 120, 200))
    exif = im.getexif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def page_count(pdf_bytes):
    return len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))


def test_pdf_name():
    assert pdf_name("scan", "x.pdf") == "scan.pdf"
    assert pdf_name("  scan.PDF ", "x.pdf") == "scan.PDF"
    assert pdf_name("", "first.pdf") == "first.pdf"
    assert pdf_name("a/b", "x.pdf") is None
    assert pdf_name("a\\b", "x.pdf") is None
    assert pdf_name("..", "") is None


def test_default_name_prefers_the_first_picture():
    assert default_name([("notes", ".txt"), ("IMG_0001", ".JPG")]) == "IMG_0001.pdf"
    assert default_name([("scan", ".dat")]) == "scan.pdf"
    assert default_name([]) == "images.pdf"


def test_folder_label():
    assert folder_label("/home/me/Documents/") == "Documents"
    assert folder_label(r"C:\Users\me\Out") == "Out"
    assert folder_label("/") == "/"


def test_is_local():
    assert is_local("/home/me/Documents")
    assert is_local(r"C:\Users\me\Documents")
    assert not is_local("ssh://host/home/me")
    assert not is_local("archive:///tmp/a.zip#dir")
    assert not is_local("s3://bucket/key")


def test_load_page_applies_exif_orientation():
    page = load_page(io.BytesIO(jpeg_rotated((40, 20))))
    assert page.size == (20, 40)


def test_load_page_flattens_transparency_onto_white():
    page = load_page(io.BytesIO(png(mode="RGBA", color=(0, 0, 0, 0))))
    assert page.mode == "RGB"
    assert page.getpixel((0, 0)) == (255, 255, 255)


def test_load_page_keeps_grayscale():
    assert load_page(io.BytesIO(png(mode="L", color=128))).mode == "L"


def test_load_page_rejects_non_images():
    with pytest.raises(Exception):
        load_page(io.BytesIO(b"not an image"))


def test_write_pdf_one_page_per_image(tmp_path):
    pages = [load_page(io.BytesIO(png((40, 20)))),
             load_page(io.BytesIO(jpeg_rotated()))]
    target = tmp_path / "out.pdf"
    write_pdf(pages, target)
    data = target.read_bytes()
    assert data.startswith(b"%PDF")
    assert page_count(data) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["out.pdf"]   # no .part left


def test_write_pdf_leaves_nothing_on_failure(tmp_path):
    class Boom:
        def save(self, *a, **k):
            open(a[0], "wb").write(b"partial")
            raise OSError("disk full")
    target = tmp_path / "out.pdf"
    with pytest.raises(OSError):
        write_pdf([Boom()], target)
    assert list(tmp_path.iterdir()) == []


def test_write_pdf_replaces_an_existing_file(tmp_path):
    target = tmp_path / "out.pdf"
    target.write_bytes(b"old")
    write_pdf([load_page(io.BytesIO(png()))], target)
    assert target.read_bytes().startswith(b"%PDF")
