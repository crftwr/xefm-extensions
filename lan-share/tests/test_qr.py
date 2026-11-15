"""The QR encoder. The digests below were checked against python-qrcode with
the same mask (and its PNGs decoded by OpenCV) when they were written; they
hold the symbol still from here on."""

import hashlib
import struct
import zlib

import pytest

from lan_share import qr

GOLDEN = [
    (b"A", 1, "c8529cd82afac26fa7f7b81f17fa4de152e3f53e14293727dece53aef0cfc86f"),
    (b"http://192.168.1.23:51234/AbCdEfGhIjKl/", 3,
     "f66651a88437d5bfe418c997136e90b7cfc4d8509db6c906b3a5d5448491ccfa"),
    (b"http://192.168.100.200:65535/" + b"x" * 60 + b"/", 6,
     "495c1d10bf92e14178794f7d987e62fb3689277c1267775a5f5762006bca2385"),
    (bytes(range(33, 127)) + b"0123456789" * 8, 9,
     "2d054892dadd4a9cf5deba33b379f4fbfeede68e7221773403b42e92f7675583"),
    (b"z" * 213, 10,
     "e1472b1a94a2ad88f3d3375976d19ad367668bbb21aa72cf386e08b16fe5ca61"),
]

SYMBOL_A = """\
#######.#..#..#######
#.....#.#####.#.....#
#.###.#...#.#.#.###.#
#.###.#.##.##.#.###.#
#.###.#..###..#.###.#
#.....#..#.##.#.....#
#######.#.#.#.#######
........##.##........
#.##.###..###.#..#.##
.#.##..#.#.####..#...
##..###.##.#.....##.#
#.##.#.....#..#####..
#..####..#..#..#..#..
........#.##..#..#..#
#######.#..##..#.#...
#.....#.##.....##.##.
#.###.#..##.#####...#
#.###.#.####..######.
#.###.#.#.#.#.##.....
#.....#...#..#.#..#.#
#######.#....#..#...."""


def _text(modules):
    return "\n".join("".join("#" if v else "." for v in row) for row in modules)


@pytest.mark.parametrize("data,version,digest", GOLDEN)
def test_symbols_match_the_golden_ones(data, version, digest):
    modules = qr.encode(data)
    assert len(modules) == version * 4 + 17
    assert hashlib.sha256(_text(modules).encode()).hexdigest() == digest


def test_a_whole_symbol():
    assert _text(qr.encode(b"A")) == SYMBOL_A


def test_capacity_and_the_largest_input():
    assert [qr.capacity(v) for v in (1, 2, 3, 9, 10)] == [14, 26, 42, 180, 213]
    assert qr.MAX_BYTES == qr.capacity(10)
    assert len(qr.encode(b"x" * 14)) == 21
    assert len(qr.encode(b"x" * 15)) == 25
    with pytest.raises(ValueError):
        qr.encode(b"x" * 214)


def test_png_is_a_valid_greyscale_image():
    png = qr.to_png(qr.encode(b"A"), scale=3, quiet=4)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    at, chunks = 8, {}
    while at < len(png):
        length, = struct.unpack(">I", png[at:at + 4])
        kind = png[at + 4:at + 8]
        body = png[at + 8:at + 8 + length]
        crc, = struct.unpack(">I", png[at + 8 + length:at + 12 + length])
        assert crc == zlib.crc32(kind + body)
        chunks[kind] = body
        at += 12 + length
    width, height, depth, colour = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    side = (21 + 8) * 3
    assert (width, height, depth, colour) == (side, side, 8, 0)
    raw = zlib.decompress(chunks[b"IDAT"])
    assert len(raw) == side * (side + 1)
    row = raw[(4 * 3) * (side + 1):][:side + 1]  # the symbol's first row
    assert row[0] == 0                          # filter: none
    assert row[1:1 + 12] == b"\xff" * 12        # quiet zone
    assert row[13:13 + 21] == b"\x00" * 21      # the finder's top edge


def test_text_draws_two_rows_a_line():
    modules = qr.encode(b"A")
    light = qr.to_text(modules, light_ink=True, quiet=2)
    assert len(light) == (21 + 4 + 1) // 2
    assert all(len(line) == 25 for line in light)
    assert light[0] == "█" * 25                 # quiet zone, inked
    dark = qr.to_text(modules, light_ink=False, quiet=2)
    assert dark[0] == " " * 25
    # the second line holds the finder's first two rows: a dark edge, then
    # dark-light-...-dark
    assert light[1][2:9] == " ▄▄▄▄▄ "
    assert dark[1][2:9] == "█▀▀▀▀▀█"
