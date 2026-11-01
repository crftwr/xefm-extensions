"""media_info.read — run with: python -m pytest tests"""

from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import pytest

from media_info import read

DATA = Path(__file__).parent / "data"


def _photo(path, orientation=1, with_gps=True):
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational as R
    image = Image.new("RGB", (40, 30), "white")
    exif = Image.Exif()
    exif[271] = "Canon"
    exif[272] = "Canon EOS R5"
    exif[274] = orientation
    sub = exif.get_ifd(0x8769)
    sub[36867] = "2024:03:15 14:30:22"
    sub[33434] = R(1, 125)
    sub[33437] = R(18, 10)
    sub[34855] = 400
    sub[37386] = R(50, 1)
    sub[42036] = "RF50mm F1.8 STM\0\0"
    if with_gps:
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2] = "N", (R(35, 1), R(39, 1), R(3089, 100))
        gps[3], gps[4] = "E", (R(139, 1), R(44, 1), R(4355, 100))
    image.save(path, exif=exif)
    return path


@pytest.fixture(autouse=True)
def _fresh_cache():
    read.clear_cache()
    yield
    read.clear_cache()


def test_kinds_by_suffix():
    assert read.kind_of("a.JPG") == "photo"
    assert read.kind_of("b.flac") == "audio"
    assert read.kind_of("c.mkv") == "video"
    assert read.kind_of("notes.txt") is None
    assert read.kind_of(".mp3") is None


def test_a_photo(tmp_path):
    fields = read.read_photo(_photo(tmp_path / "p.jpg"))
    assert fields["dimensions"] == "40 × 30"
    assert fields["date"] == datetime(2024, 3, 15, 14, 30, 22).timestamp()
    assert fields["camera"] == "Canon EOS R5"
    assert fields["lens"] == "RF50mm F1.8 STM"
    assert fields["exposure"] == "1/125 s · f/1.8 · ISO 400 · 50 mm"
    assert fields["location"] == "35.65858° N, 139.74543° E"


def test_a_turned_photo_gives_what_is_seen(tmp_path):
    fields = read.read_photo(_photo(tmp_path / "p.jpg", orientation=6, with_gps=False))
    assert fields["dimensions"] == "30 × 40"
    assert "location" not in fields


def test_a_song():
    fields = read.read_av(DATA / "tone.m4a")
    assert fields["duration"] == pytest.approx(2.0, abs=0.1)
    assert (fields["title"], fields["artist"], fields["album"]) == \
        ("Test Tone", "Media Info", "Fixtures")
    assert (fields["year"], fields["track"], fields["genre"]) == ("2024", "3/12", "Test")
    assert fields["audio"] == "AAC · 44.1 kHz · stereo"
    assert "dimensions" not in fields


def test_a_video():
    fields = read.read_av(DATA / "clip.mp4")
    assert fields["dimensions"] == "64 × 48"
    assert fields["video"] == "MPEG-4 Visual · 25 fps"
    assert fields["duration"] == pytest.approx(1.0, abs=0.1)
    assert fields["date"] == datetime(2024, 3, 15, 14, 30, 22, tzinfo=timezone.utc).timestamp()


def test_what_is_not_media_has_nothing(tmp_path):
    (tmp_path / "x.txt").write_text("hi")
    (tmp_path / "broken.jpg").write_bytes(b"not a jpeg")
    (tmp_path / "broken.mp3").write_bytes(b"not audio")
    assert read.metadata(tmp_path / "x.txt") == {}
    assert read.metadata(tmp_path / "broken.jpg") == {}
    assert read.metadata(tmp_path / "broken.mp3") == {}


def test_a_file_is_read_once_until_it_changes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(read, "read_av", lambda p: calls.append(p) or {"duration": 1.0})
    for _ in range(3):
        read.metadata(tmp_path / "a.mp3", 10, 1.0)
    read.metadata(tmp_path / "a.mp3", 11, 2.0)
    assert len(calls) == 2


@pytest.mark.parametrize("value,text", [
    ((Fraction(1, 4000), None, None, None), "1/4000 s"),
    ((Fraction(2, 1), Fraction(8), (100, 0), None), "2 s · f/8 · ISO 100"),
    ((None, None, None, None), None),
])
def test_exposure_text(value, text):
    assert read.exposure_text(*value) == text


def test_camera_names_are_not_repeated():
    assert read.join_camera("NIKON CORPORATION", "NIKON Z 6") == "NIKON Z 6"
    assert read.join_camera("Apple", "iPhone 15 Pro") == "Apple iPhone 15 Pro"
    assert read.join_camera(None, " X100V\0") == "X100V"
