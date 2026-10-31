"""The attribute providers XeFM calls: ``read(directory, entries)``, one value
per entry. Each asks :func:`media_info.read.metadata` for its one field, so a
file is read once for all of them."""

import os

from media_info.read import kind_of, metadata


def _field(name):
    def read(directory, entries):
        out = []
        for entry in entries:
            if entry.is_dir or kind_of(entry.name) is None:
                out.append(None)
                continue
            try:
                stamp = (entry.size, entry.mtime)
            except OSError:
                out.append(None)
                continue
            out.append(metadata(entry.path, *stamp).get(name))
        return out
    read.__name__ = name
    read.__doc__ = f"The {name} of each media entry, None for any other."
    return read


dimensions = _field("dimensions")
date = _field("date")
camera = _field("camera")
lens = _field("lens")
exposure = _field("exposure")
location = _field("location")
duration = _field("duration")
title = _field("title")
artist = _field("artist")
album = _field("album")
year = _field("year")
track = _field("track")
genre = _field("genre")
bitrate = _field("bitrate")
video = _field("video")
audio = _field("audio")

#: How many entries of a folder the extra's ``when`` looks at.
_SAMPLE = 500


def media_folder(path) -> bool:
    """Whether ``path`` is a folder of media: of the first few hundred files
    in it, at least half are photos, songs or videos. Local folders only, as
    the attributes are."""
    if getattr(path, "scheme", "file") != "file":
        return False
    files = media = 0
    try:
        with os.scandir(str(path)) as it:
            for entry in it:
                if files >= _SAMPLE:
                    break
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                files += 1
                if kind_of(entry.name) is not None:
                    media += 1
    except OSError:
        return False
    return media > 0 and media * 2 >= files
