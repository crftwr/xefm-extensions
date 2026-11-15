"""A small QR code encoder: byte mode, error correction level M, versions 1
to 10 (up to 213 bytes). That is all a URL on the local network needs, and it
keeps the package free of dependencies: nothing to sync before the first
share.

``encode(data)`` returns the symbol as rows of booleans (True = dark), without
the quiet zone. ``to_png`` and ``to_text`` draw it.
"""

import struct
import zlib

# Per version (index 0 = version 1), level M: error correction codewords per
# block, then the block sizes in data codewords.
_BLOCKS = [
    (10, [16]),
    (16, [28]),
    (26, [44]),
    (18, [32, 32]),
    (24, [43, 43]),
    (16, [27, 27, 27, 27]),
    (18, [31, 31, 31, 31]),
    (22, [38, 38, 39, 39]),
    (22, [36, 36, 36, 37, 37]),
    (26, [43, 43, 43, 43, 44]),
]
_ALIGNMENT = [
    [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34],
    [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50],
]
MAX_BYTES = 213


def capacity(version):
    """How many bytes a symbol of ``version`` holds."""
    count_bits = 8 if version <= 9 else 16
    return (sum(_BLOCKS[version - 1][1]) * 8 - 4 - count_bits) // 8


def encode(data):
    """The QR symbol for ``data`` (bytes): a list of rows, True where dark.
    ValueError when it does not fit in version 10."""
    data = bytes(data)
    for version in range(1, len(_BLOCKS) + 1):
        if len(data) <= capacity(version):
            break
    else:
        raise ValueError(f"{len(data)} bytes do not fit in a QR code here "
                         f"(at most {MAX_BYTES})")
    codewords = _interleave(version, _data_codewords(version, data))
    size = version * 4 + 17
    modules = [[False] * size for _ in range(size)]
    function = [[False] * size for _ in range(size)]
    _draw_function_patterns(version, modules, function)
    _draw_codewords(codewords, modules, function)

    best = None
    for mask in range(8):
        _apply_mask(mask, modules, function)
        _draw_format_bits(mask, modules, function)
        penalty = _penalty(modules)
        if best is None or penalty < best[0]:
            best = (penalty, mask)
        _apply_mask(mask, modules, function)        # XOR again: undo
    mask = best[1]
    _apply_mask(mask, modules, function)
    _draw_format_bits(mask, modules, function)
    return modules


# --------------------------------------------------------------------------- #
# Codewords
# --------------------------------------------------------------------------- #

def _data_codewords(version, data):
    total = sum(_BLOCKS[version - 1][1])
    bits = []

    def put(value, length):
        bits.extend((value >> i) & 1 for i in reversed(range(length)))

    put(0b0100, 4)                                  # byte mode
    put(len(data), 8 if version <= 9 else 16)
    for byte in data:
        put(byte, 8)
    put(0, min(4, total * 8 - len(bits)))           # terminator
    put(0, -len(bits) % 8)
    out = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(out) < total:
        out.append(pad)
        pad ^= 0xEC ^ 0x11
    return out


def _interleave(version, data):
    ec_len, sizes = _BLOCKS[version - 1]
    divisor = _rs_divisor(ec_len)
    blocks, ec_blocks, at = [], [], 0
    for size in sizes:
        block = data[at:at + size]
        at += size
        blocks.append(block)
        ec_blocks.append(_rs_remainder(block, divisor))
    out = []
    for i in range(max(sizes)):
        out.extend(block[i] for block in blocks if i < len(block))
    for i in range(ec_len):
        out.extend(block[i] for block in ec_blocks)
    return out


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for i, coefficient in enumerate(divisor):
            result[i] ^= _gf_mul(coefficient, factor)
    return result


# --------------------------------------------------------------------------- #
# Drawing the symbol. Coordinates are (x, y) = (column, row).
# --------------------------------------------------------------------------- #

def _draw_function_patterns(version, modules, function):
    size = len(modules)

    def put(x, y, dark):
        modules[y][x] = dark
        function[y][x] = True

    for i in range(size):                           # timing
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):   # finders
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    positions = _ALIGNMENT[version - 1]
    last = len(positions) - 1
    for i, cx in enumerate(positions):              # alignment
        for j, cy in enumerate(positions):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue                            # a finder is there
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    put(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    _draw_format_bits(0, modules, function)         # reserves the area
    if version >= 7:
        rem = version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = version << 12 | rem
        for i in range(18):
            dark = (bits >> i) & 1 == 1
            a, b = size - 11 + i % 3, i // 3
            put(a, b, dark)
            put(b, a, dark)


def _draw_format_bits(mask, modules, function):
    size = len(modules)
    data = mask                                     # level M is 0b00
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412

    def put(x, y, i):
        modules[y][x] = (bits >> i) & 1 == 1
        function[y][x] = True

    for i in range(6):
        put(8, i, i)
    put(8, 7, 6)
    put(8, 8, 7)
    put(7, 8, 8)
    for i in range(9, 15):
        put(14 - i, 8, i)
    for i in range(8):
        put(size - 1 - i, 8, i)
    for i in range(8, 15):
        put(8, size - 15 + i, i)
    modules[size - 8][8] = True                     # always dark
    function[size - 8][8] = True


def _draw_codewords(codewords, modules, function):
    size = len(modules)
    total = len(codewords) * 8
    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:                              # skip the timing column
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = (right + 1) & 2 == 0
                y = size - 1 - vert if upward else vert
                if not function[y][x] and i < total:
                    modules[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2


_MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]


def _apply_mask(mask, modules, function):
    invert = _MASKS[mask]
    for y, row in enumerate(modules):
        for x in range(len(row)):
            if not function[y][x] and invert(x, y):
                row[x] = not row[x]


_FINDER_LIKE = (True, False, True, True, True, False, True)


def _penalty(modules):
    """The standard's four penalty rules; the lowest total picks the mask."""
    size = len(modules)
    result = 0
    columns = [[modules[y][x] for y in range(size)] for x in range(size)]
    for line in modules + columns:
        run, colour = 0, None
        for dark in line:                           # rule 1: runs of 5 or more
            if dark == colour:
                run += 1
                if run == 5:
                    result += 3
                elif run > 5:
                    result += 1
            else:
                run, colour = 1, dark
        for i in range(size - 6):                   # rule 3: finder look-alikes
            if tuple(line[i:i + 7]) == _FINDER_LIKE:
                before = line[max(0, i - 4):i]
                after = line[i + 7:i + 11]
                if (len(before) == 4 and not any(before)) or \
                        (len(after) == 4 and not any(after)):
                    result += 40
    for y in range(size - 1):                       # rule 2: 2x2 blocks
        for x in range(size - 1):
            if modules[y][x] == modules[y][x + 1] == \
                    modules[y + 1][x] == modules[y + 1][x + 1]:
                result += 3
    dark = sum(sum(row) for row in modules)         # rule 4: balance
    total = size * size
    result += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
    return result


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def to_png(modules, *, scale=6, quiet=4):
    """The symbol as PNG bytes: dark on white, ``scale`` pixels a module, with
    a quiet zone of ``quiet`` modules, which a scanner needs."""
    size = len(modules) + 2 * quiet
    blank = b"\xff" * (size * scale)
    rows = []
    for y in range(size):
        my = y - quiet
        if 0 <= my < len(modules):
            line = bytearray(blank)
            for mx, dark in enumerate(modules[my]):
                if dark:
                    start = (mx + quiet) * scale
                    line[start:start + scale] = b"\x00" * scale
            line = bytes(line)
        else:
            line = blank
        rows.extend([b"\x00" + line] * scale)       # filter type 0 per scanline

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body)))

    side = size * scale
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b""))


def to_text(modules, *, light_ink=True, quiet=2):
    """The symbol as lines of half-block characters, two module rows a line,
    for a terminal. Text has one colour, so which modules get the ink depends
    on the screen: ``light_ink=True`` suits light text on a dark background
    (the light modules and the quiet zone are drawn, the dark ones left
    empty), ``False`` dark text on a light one."""
    size = len(modules) + 2 * quiet

    def ink(x, y):
        mx, my = x - quiet, y - quiet
        inside = 0 <= mx < len(modules) and 0 <= my < len(modules)
        dark = inside and modules[my][mx]
        return dark != light_ink

    lines = []
    for y in range(0, size, 2):
        chars = []
        for x in range(size):
            top = ink(x, y)
            bottom = ink(x, y + 1) if y + 1 < size else not light_ink
            chars.append(" ▄▀█"[top * 2 + bottom])
        lines.append("".join(chars))
    return lines
