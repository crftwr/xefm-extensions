"""The Classic Blue theme, in the shape config.py's THEMES takes: colors are
(R, G, B) tuples, 0-255, and anything not named here comes from Dark+.

It is a Python dict rather than a [contributes.themes] table in the manifest
because TOML has no tuples, and a theme whose colors arrive as lists crashes
XeFM when it is selected (crftwr/xefm#708). Once XeFM normalizes them, this
can move back into the manifest as plain data."""

CLASSIC_BLUE = {
    "base": "Dark+",
    "background": (0, 0, 128),          # the blue
    "foreground": (85, 255, 255),       # cyan text
    "muted": (128, 168, 216),
    "accent": (0, 170, 170),
    "accent2": (255, 255, 85),
    "surface": (0, 0, 168),             # pane header, popups
    "selection": (0, 100, 112),         # selected rows
    "status": (0, 128, 128),            # bottom status bar
    "footer": (0, 0, 168),              # per-pane info bar
    "isearch_match": (255, 255, 85),
    "file_types": {
        "directory": (255, 255, 255),   # folders in white
        "file": (85, 255, 255),         # files in cyan
        "link": (85, 255, 85),          # symlinks in green
        "hidden": 0.35,                 # hidden entries fade toward the blue
    },
    "cursor": {
        "active": (255, 255, 85),       # yellow cursor cue in the focused pane
        "inactive": (120, 144, 208),
    },
    "syntax": {
        "keyword": (255, 255, 85),
        "string": (85, 255, 85),
        "comment": (128, 168, 216),
        "number": (255, 170, 255),
        "operator": (255, 255, 255),
        "builtin": (255, 200, 120),
        "name": (85, 255, 255),
    },
}
