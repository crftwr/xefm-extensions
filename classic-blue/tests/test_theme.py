"""The theme is data, so the tests check the data: every color is an RGB
tuple (a list crashes XeFM, crftwr/xefm#708), and the text XeFM draws on the
blue stays readable (WCAG contrast ratio, 4.5:1 for text, 3:1 for the cursor
cue)."""

import pytest

from classic_blue.theme import CLASSIC_BLUE as THEME


def luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def colors(table, prefix=""):
    for key, value in table.items():
        if isinstance(value, dict):
            yield from colors(value, f"{prefix}{key}.")
        elif not isinstance(value, (str, float)):
            yield f"{prefix}{key}", value


def test_based_on_a_builtin():
    assert THEME["base"] == "Dark+"


@pytest.mark.parametrize("name,rgb", list(colors(THEME)))
def test_every_color_is_rgb(name, rgb):
    assert isinstance(rgb, tuple), name
    assert len(rgb) == 3 and all(isinstance(c, int) and 0 <= c <= 255 for c in rgb), name


@pytest.mark.parametrize("fg", [
    "foreground", "file_types.directory", "file_types.file", "file_types.link",
    "syntax.keyword", "syntax.string", "syntax.number", "syntax.operator",
    "syntax.builtin", "syntax.name", "isearch_match",
])
def test_text_is_readable_on_the_blue(fg):
    rgb = dict(colors(THEME))[fg]
    assert contrast(rgb, THEME["background"]) >= 4.5, fg


@pytest.mark.parametrize("bg", ["selection", "surface", "footer"])
def test_text_is_readable_on_bars_and_selection(bg):
    assert contrast(THEME["foreground"], THEME[bg]) >= 4.5, bg


def test_comments_recede_but_stay_legible():
    ratio = contrast(THEME["syntax"]["comment"], THEME["background"])
    assert 3 <= ratio < contrast(THEME["foreground"], THEME["background"])


def test_cursor_cue_stands_out():
    assert contrast(THEME["cursor"]["active"], THEME["background"]) >= 3
