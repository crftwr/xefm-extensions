"""On Linux and macOS ``a.exe:Zone.Identifier`` is an ordinary file name, so
the stream is simulated by a file of that name next to the file. The code is
the same one that opens the NTFS stream on Windows."""

import codecs
import sys

import pytest

from unblock_files.logic import (
    Mark, STREAM, confirm_prompt, decode, is_local, parse_mark, read_mark,
    remove_mark, result_markdown, stream_path)


BROWSER = ("[ZoneTransfer]\r\nZoneId=3\r\n"
           "ReferrerUrl=https://example.com/downloads\r\n"
           "HostUrl=https://dl.example.com/files/setup.exe\r\n")


def marked(tmp_path, name="setup.exe", text=BROWSER, data=None):
    f = tmp_path / name
    f.write_bytes(b"MZ")
    if sys.platform != "win32":
        (tmp_path / f"{name}:{STREAM}").write_bytes(
            data if data is not None else text.encode())
    else:   # the real stream
        with open(stream_path(f), "wb") as s:
            s.write(data if data is not None else text.encode())
    return f


def test_parse_a_browser_mark():
    mark = parse_mark(BROWSER)
    assert mark == Mark(3, "https://dl.example.com/files/setup.exe",
                        "https://example.com/downloads")
    assert mark.zone_name == "Internet"
    assert mark.source == "dl.example.com"


def test_parse_minimal_and_odd_marks():
    assert parse_mark("[ZoneTransfer]\nZoneId=3").source == "Internet"
    assert parse_mark("[zonetransfer]\nzoneid = 4\nHostUrl=about:internet").source \
        == "Restricted sites"
    assert parse_mark("[Other]\nZoneId=3").zone is None
    assert parse_mark("[ZoneTransfer]\nZoneId=x").source == "unknown zone"
    assert parse_mark("[ZoneTransfer]\nZoneId=7").zone_name == "zone 7"


def test_referrer_is_the_source_when_there_is_no_host_url():
    assert parse_mark("[ZoneTransfer]\nZoneId=3\nReferrerUrl=https://a.example/x").source \
        == "a.example"


def test_decode_utf16_and_bom():
    assert decode(codecs.BOM_UTF16_LE + "ZoneId=3".encode("utf-16-le")) == "ZoneId=3"
    assert decode(codecs.BOM_UTF8 + b"ZoneId=3") == "ZoneId=3"
    assert decode(b"ZoneId=3\xff").startswith("ZoneId=3")


def test_read_and_remove(tmp_path):
    f = marked(tmp_path)
    assert read_mark(f).source == "dl.example.com"
    assert remove_mark(f) is True
    assert read_mark(f) is None
    assert remove_mark(f) is False
    assert f.read_bytes() == b"MZ"          # the file itself is untouched


def test_unmarked_file(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("hi")
    assert read_mark(f) is None
    assert remove_mark(f) is False


def test_utf16_stream(tmp_path):
    f = marked(tmp_path, data=codecs.BOM_UTF16_LE + BROWSER.encode("utf-16-le"))
    assert read_mark(f).zone == 3


def test_volume_without_streams_counts_as_unmarked(monkeypatch, tmp_path):
    err = OSError(22, "The filename, directory name, or volume label syntax is incorrect")
    err.winerror = 123

    def refuse(*a, **k):
        raise err
    monkeypatch.setattr("builtins.open", refuse)
    assert read_mark(tmp_path / "x") is None
    monkeypatch.setattr("os.remove", refuse)
    assert remove_mark(tmp_path / "x") is False


def test_other_errors_are_raised(monkeypatch, tmp_path):
    def denied(*a, **k):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr("os.remove", denied)
    with pytest.raises(PermissionError):
        remove_mark(tmp_path / "x")


def test_is_local():
    assert is_local(r"C:\Users\me\Downloads\a.exe")
    assert is_local(r"\\server\share\a.exe")
    assert not is_local("archive://C:/a.zip#b.exe")
    assert not is_local("ssh://host/a.exe")


def test_confirm_prompt():
    m = lambda host: Mark(3, f"https://{host}/f")   # noqa: E731
    one = confirm_prompt([("a", m("x.example"))])
    assert one == "Unblock 1 file downloaded from x.example?"
    many = confirm_prompt([(str(i), m(f"h{i}.example")) for i in range(5)]
                          + [("dup", m("h0.example"))])
    assert "6 files" in many and len(many) < 100 and "h0.example, h1.example, h2.example and 2 more" in many


def test_result_markdown():
    out = result_markdown([("setup.exe", parse_mark(BROWSER))], 2,
                          [("locked.exe", "Access is denied")], md_escape=lambda s: s)
    assert "**Unblocked** (1)" in out and "dl.example.com" in out
    assert "2 files had no mark." in out
    assert "locked.exe: Access is denied" in out
    assert result_markdown([], 0, [], md_escape=str) == "Nothing to do."
