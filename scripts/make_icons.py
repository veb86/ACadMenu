#!/usr/bin/env python3
"""Draw the 16x16 and 32x32 icons of the Bobrov ribbon commands.

Only the Python standard library is used, so the PNG files are reproducible:

    python3 scripts/make_icons.py            # rewrite the PNG files in src/BobrovMenu.cuix
    python3 scripts/make_icons.py --check    # fail if the committed PNG files differ
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUIX_SOURCE = ROOT / "src" / "BobrovMenu.cuix"

TRANSPARENT = (0, 0, 0, 0)
BORDER = (0x37, 0x47, 0x4F, 0xFF)  # dark blue-grey frame, visible on light and dark ribbons
TITLE = (0x1E, 0x88, 0xE5, 0xFF)  # blue title bar
BODY = (0xFF, 0xFF, 0xFF, 0xFF)  # white palette body
DIVIDER = (0xCF, 0xD8, 0xDC, 0xFF)  # light grid line between names and values
LABEL = (0x90, 0xA4, 0xAE, 0xFF)  # property names
VALUE = (0x42, 0xA5, 0xF5, 0xFF)  # property values


def fill(pixels, x0, y0, x1, y1, color):
    """Fill the inclusive rectangle (x0, y0)-(x1, y1)."""
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            pixels[y][x] = color


def frame(pixels, x0, y0, x1, y1, color):
    fill(pixels, x0, y0, x1, y0, color)
    fill(pixels, x0, y1, x1, y1, color)
    fill(pixels, x0, y0, x0, y1, color)
    fill(pixels, x1, y0, x1, y1, color)


def draw_32():
    px = [[TRANSPARENT] * 32 for _ in range(32)]
    fill(px, 2, 3, 29, 28, BODY)
    fill(px, 3, 4, 28, 8, TITLE)
    frame(px, 2, 3, 29, 28, BORDER)
    fill(px, 3, 9, 28, 9, BORDER)
    fill(px, 13, 11, 13, 26, DIVIDER)
    for y in (12, 16, 20, 24):
        fill(px, 5, y, 11, y + 1, LABEL)
        fill(px, 15, y, 26, y + 1, VALUE)
    return px


def draw_16():
    px = [[TRANSPARENT] * 16 for _ in range(16)]
    fill(px, 1, 1, 14, 14, BODY)
    fill(px, 2, 2, 13, 4, TITLE)
    frame(px, 1, 1, 14, 14, BORDER)
    fill(px, 2, 5, 13, 5, BORDER)
    fill(px, 6, 7, 6, 12, DIVIDER)
    for y in (7, 9, 11):
        fill(px, 3, y, 4, y, LABEL)
        fill(px, 8, y, 12, y, VALUE)
    return px


SYMBOL_COLORS = {
    ".": TRANSPARENT,
    "B": (0x29, 0x86, 0xDB, 0xFF),  # leader or database outline
    "L": (0xAB, 0xDB, 0xFF, 0xFF),  # surface highlights
    "G": (0x23, 0xA3, 0x68, 0xFF),  # addition and refresh arrows
    "T": (0x14, 0x9D, 0xA1, 0xFF),  # second grouped leader
    "P": (0x83, 0x61, 0xC4, 0xFF),  # rules and checklist
    "W": BODY,
    "O": (0xEB, 0x99, 0x30, 0xFF),  # database pencil
    "D": BORDER,
}

SYMBOLS = {
    "SL_CREATE": """
        ................
        ...........GG...
        ...........GG...
        .........GGGGGG.
        .........GGGGGG.
        ...........GG...
        .......BB..GG...
        ......BBBBBBBB..
        .....BB.........
        ....BB..........
        ...BB...........
        ..BBB...........
        ..BBBB..........
        ..BB............
        ................
        ................
    """,
    "SL_CREATE_GROUP": """
        ................
        ...........GG...
        ...........GG...
        .........GGGGGG.
        .......BBGGGGGG.
        ......BB...GG...
        .....BB....GG...
        ....BB..........
        ...BBB.TTTTTTT..
        ..BBBBTTTTTTTT..
        ..BB.TT.........
        ....TT..........
        ...TTT..........
        ...TTTT.........
        ...TT...........
        ................
    """,
    "SL_UPDATE": """
        ................
        ......GGGG..GG..
        ....GGGGGGG.GG..
        ...GG......GGG..
        ..GG......GGGG..
        ..GG.....GGGGG..
        .GG.............
        .GG.............
        .............GG.
        .............GG.
        ..GGGGG.....GG..
        ..GGGG......GG..
        ..GGG......GG...
        ..GG.GGGGGGG....
        ..GG..GGGG......
        ................
    """,
    "SL_RULES": """
        ................
        ...PPPPPPPP.....
        ...PWWWWWWPP....
        ...PWWWWWWPWP...
        ...PWWWWWWPPPP..
        ...PWWWWWWWWWP..
        ...PWPWWWWWWWP..
        ...PWPWPPPPPWP..
        ...PWWWWWWWWWP..
        ...PWPWPPPPPWP..
        ...PWWWWWWWWWP..
        ...PWPWPPPPPWP..
        ...PWWWWWWWWWP..
        ...PWWWWWWWWWP..
        ...PPPPPPPPPPP..
        ................
    """,
    "DB_EDIT": """
        ................
        .....BBBBB......
        ...BBLLLLLBB....
        ..BLLLLLLLLLB...
        ..BBLLLLLLLBB...
        ..BLBBBBBBBLB...
        ..BLLLLLLLLLB...
        ..BBLLLLLLLBB.O.
        ..BLBBBBBBB..OOO
        ..BLLLLLLL..OOO.
        ..BBLLLLL..OOO..
        ..BLBBBB..OOO...
        ..BLLLLL.OOO....
        ...BBLLDDOO.....
        .....BBDD.......
        ................
    """,
}


def draw_symbol(symbol, scale):
    rows = SYMBOLS[symbol].split()
    return [
        [SYMBOL_COLORS[code] for code in row for _ in range(scale)]
        for row in rows
        for _ in range(scale)
    ]


def png_bytes(pixels):
    """Encode RGBA rows as a PNG file (filter 0, deterministic zlib level 9)."""
    height = len(pixels)
    width = len(pixels[0])
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in pixels)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


ICONS = {
    "BOBROV_XDATAPALETTE_16.png": draw_16,
    "BOBROV_XDATAPALETTE_32.png": draw_32,
    **{
        f"BOBROV_{symbol}_{16 * scale}.png": lambda symbol=symbol, scale=scale: draw_symbol(symbol, scale)
        for symbol in SYMBOLS
        for scale in (1, 2)
    },
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only compare with the committed files")
    args = parser.parse_args(argv)

    stale = []
    for name, draw in ICONS.items():
        target = CUIX_SOURCE / name
        data = png_bytes(draw())
        if args.check:
            if not target.exists() or target.read_bytes() != data:
                stale.append(name)
        else:
            target.write_bytes(data)
            print("written", target.relative_to(ROOT))
    if stale:
        print("Icons differ from scripts/make_icons.py: " + ", ".join(stale), file=sys.stderr)
        print("Run: python3 scripts/make_icons.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
