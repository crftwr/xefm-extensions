import hashlib
import io

import pytest

from compute_hash import logic
from compute_hash.logic import (
    ALGORITHMS, Stopped, checksum_line, digest_stream, error_text,
    ordered_algorithms, progress_detail)


def test_ordered_algorithms_puts_last_used_first():
    names = [name for _, name in ordered_algorithms("sha512")]
    assert names[0] == "sha512"
    assert sorted(names) == sorted(name for _, name in ALGORITHMS)


def test_ordered_algorithms_keeps_default_order_without_a_last():
    assert ordered_algorithms(None) == ALGORITHMS
    assert ordered_algorithms("crc32") == ALGORITHMS


@pytest.mark.parametrize("label,name", ALGORITHMS)
def test_digest_stream_matches_hashlib(label, name):
    data = b"abc" * 1000
    assert digest_stream(io.BytesIO(data), name) == hashlib.new(name, data).hexdigest()


def test_digest_stream_reads_across_chunks(monkeypatch):
    monkeypatch.setattr(logic, "CHUNK_SIZE", 4)
    data = b"0123456789"
    assert digest_stream(io.BytesIO(data), "sha256") == hashlib.sha256(data).hexdigest()


def test_digest_stream_of_empty_file():
    assert digest_stream(io.BytesIO(b""), "sha256") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


def test_digest_stream_stops_when_asked(monkeypatch):
    monkeypatch.setattr(logic, "CHUNK_SIZE", 1)
    asked = []

    def should_stop():
        asked.append(1)
        return len(asked) > 2

    with pytest.raises(Stopped):
        digest_stream(io.BytesIO(b"abcdef"), "md5", should_stop)


def test_checksum_line_plain():
    assert checksum_line("ab12", "setup.exe") == "ab12  setup.exe"


def test_checksum_line_escapes_like_coreutils():
    assert checksum_line("ab12", "a\\b\nc") == "\\ab12  a\\\\b\\nc"


def test_error_text():
    assert error_text(PermissionError(13, "Permission denied")) == "Permission denied"
    assert error_text(ValueError("bad")) == "bad"
    assert error_text(RuntimeError()) == "RuntimeError"


def test_digest_stream_reports_bytes_read(monkeypatch):
    monkeypatch.setattr(logic, "CHUNK_SIZE", 4)
    seen = []
    digest_stream(io.BytesIO(b"0123456789"), "md5", on_read=seen.append)
    assert seen == [4, 8, 10]


def test_progress_detail():
    assert progress_detail("big.bin", 512, 2048) == "big.bin — 25%"
    assert progress_detail("big.bin", 512, 0) == "big.bin"
