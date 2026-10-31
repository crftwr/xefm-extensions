# Media Info

An [XeFM](https://github.com/crftwr/xefm) extension: what photos, songs and
videos say about themselves — a photo's camera and exposure, a song's artist
and length, a video's resolution and codecs — as XeFM attributes. They show in
**File Details**, as columns in a folder of media, and you can sort by them.

```
| Dimensions | 6000 × 4000 |
| Date taken | 2024-05-01 09:10:11 |
| Camera     | FUJIFILM X100V |
| Lens       | XF23mmF2 R WR |
| Exposure   | 1/250 s · f/2 · ISO 200 · 23 mm |
| Location   | 35.65858° N, 139.74543° E |
```

## Install

Needs XeFM 1.12.0 or later. The desktop app and the terminal app share
`~/.xefm`, so either way below installs it for both.

**Inside XeFM** (desktop app or terminal): choose **Tools ▸ Advanced ▸ Install
Extension…** and paste

```text
github:crftwr/xefm-extensions/media-info
```

XeFM downloads and checks the package and lists what it adds: sixteen
attributes, the **Media** extra, and the Python package `pymediainfo`. Choose
**Install** (the dialog starts on Cancel) and accept the package sync it
offers; XeFM reloads its configuration.

**With the `xefm` command** (pip, pipx, uv or the Homebrew formula):

```bash
xefm ext install github:crftwr/xefm-extensions/media-info
```

Accept the sync it offers (or run `xefm deps sync` afterwards), then run
**Tools ▸ Reload Configuration** in XeFM, or restart it.

## Use

**File Details** on a photo, a song or a video lists what could be read:

| Kind | Fields |
|---|---|
| Photo | Dimensions, Date taken, Camera, Lens, Exposure, Location |
| Audio | Duration, Title, Artist, Album, Year, Track, Genre, Bit rate, Audio |
| Video | Dimensions, Date taken, Duration, Bit rate, Video, Audio |

A field the file does not carry gets no row. Location is the GPS position
stored in the photo, shown as it is: nothing is looked up, and nothing is sent
anywhere.

In a folder where at least half the files are media, the **Media** extra adds
a **Duration** and a **Dimensions** column beside the size. Turn it on or off
for a tab under **View ▸ Show ▸ Media**. A narrow pane drops these two columns
before the date. The sort dialog offers whatever the pane shows, so with the
extra on you can sort a folder by duration or dimensions. Any of the
attributes — `media.artist`, `media.camera`, `media.date` and the rest — can
go in a layout of your own, and is then a column to sort by too:

```python
LAYOUTS = {
    'music': {'label': 'Music', 'columns': [
        'name', 'media.artist', 'media.album', 'media.duration']},
}
```

Only files on the local disk are read — not `ssh://`, `s3://` or archive
members — and only what the file says in its header, not the whole file.

## What it reads with

- **Photos:** Pillow, which XeFM already ships. JPEG, TIFF, PNG, WebP and DNG
  read everywhere; HEIC and AVIF read when Pillow has a plugin for them.
- **Audio and video:** [pymediainfo](https://pypi.org/project/pymediainfo/)
  (MIT), whose wheels for macOS, Windows and Linux bundle the MediaInfo
  library (BSD-2-Clause). Nothing here is GPL, and no external program is
  needed.

## Develop

```bash
xefm ext check media-info
cd media-info && python -m pytest tests
```

The tests need Pillow and pymediainfo, not XeFM. `tests/data/` holds a
two-second song and a one-second video made for them.

This package uses only XeFM's public API (`xefm.user_api.__all__`).
