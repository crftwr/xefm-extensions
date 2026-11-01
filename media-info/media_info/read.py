"""Reading a file's media metadata into one flat dict.

Photos go through Pillow (XeFM ships it), audio and video through
pymediainfo, whose wheels bundle MediaInfo (BSD-2-Clause). Both read only
what they need of the file, not all of it. Nothing here imports XeFM, so it
is tested on its own.

A file is read once however many attributes ask about it: :func:`metadata`
keeps the last few hundred results, keyed by path, size and mtime, so the
fifteen attribute providers that each want one field share one read.
"""

import logging
import threading
from collections import OrderedDict
from datetime import datetime

logger = logging.getLogger(__name__)

PHOTO = frozenset({".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".png", ".webp",
                   ".heic", ".heif", ".avif", ".dng"})
AUDIO = frozenset({".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus",
                   ".wav", ".aif", ".aiff", ".wma", ".alac", ".ape", ".wv"})
VIDEO = frozenset({".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv",
                   ".mpg", ".mpeg", ".ts", ".m2ts", ".mts", ".3gp", ".flv"})


def kind_of(name: str):
    """``'photo'``, ``'audio'``, ``'video'`` or None, by the name's suffix."""
    dot = name.rfind(".")
    suffix = name[dot:].lower() if dot > 0 else ""
    if suffix in PHOTO:
        return "photo"
    if suffix in AUDIO:
        return "audio"
    if suffix in VIDEO:
        return "video"
    return None


# --- the cache ------------------------------------------------------------------

_CACHE_SIZE = 512
_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_lock = threading.Lock()


def metadata(path, size=None, mtime=None) -> dict:
    """Every field this package knows for ``path``, ``{}`` for a file that is
    not media or cannot be read. ``size`` and ``mtime`` tell a changed file
    from the one read before."""
    kind = kind_of(str(path))
    if kind is None:
        return {}
    key = (str(path), size, mtime)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    fields = read_photo(path) if kind == "photo" else read_av(path)
    with _lock:
        _cache[key] = fields
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return fields


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# --- photos -----------------------------------------------------------------------

_EXIF_IFD, _GPS_IFD = 0x8769, 0x8825
_MAKE, _MODEL, _ORIENTATION, _DATETIME = 271, 272, 274, 306
_EXPOSURE, _FNUMBER, _ISO, _TAKEN, _FOCAL, _LENS = 33434, 33437, 34855, 36867, 37386, 42036


def read_photo(path) -> dict:
    try:
        from PIL import Image
    except ImportError:
        return {}
    try:
        with Image.open(str(path)) as image:
            width, height = image.size
            exif = image.getexif()
            sub = exif.get_ifd(_EXIF_IFD)
            gps = exif.get_ifd(_GPS_IFD)
    except Exception as e:  # noqa: BLE001 — an unreadable photo has no metadata
        logger.debug(f"media-info: cannot read {path}: {e}")
        return {}
    out = {}
    # Orientations 5–8 turn the picture a quarter: say what is seen.
    if exif.get(_ORIENTATION) in (5, 6, 7, 8):
        width, height = height, width
    out["dimensions"] = dimensions(width, height)
    taken = exif_time(sub.get(_TAKEN) or exif.get(_DATETIME))
    if taken is not None:
        out["date"] = taken
    camera = join_camera(exif.get(_MAKE), exif.get(_MODEL))
    if camera:
        out["camera"] = camera
    lens = clean(sub.get(_LENS))
    if lens:
        out["lens"] = lens
    exposure = exposure_text(sub.get(_EXPOSURE), sub.get(_FNUMBER), sub.get(_ISO),
                             sub.get(_FOCAL))
    if exposure:
        out["exposure"] = exposure
    where = gps_text(gps)
    if where:
        out["location"] = where
    return out


def dimensions(width, height) -> str:
    return f"{int(width)} × {int(height)}"


def clean(value):
    """EXIF text without the NUL padding and spaces cameras leave on it."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    text = str(value).replace("\0", "").strip()
    return text or None


def join_camera(make, model):
    make, model = clean(make), clean(model)
    if make and model and model.lower().startswith(make.split()[0].lower()):
        return model                       # "Canon Canon EOS R5" reads twice
    return " ".join(p for p in (make, model) if p) or None


def exif_time(value):
    """An EXIF ``YYYY:MM:DD HH:MM:SS`` (camera local time) as a timestamp."""
    text = clean(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:19], "%Y:%m:%d %H:%M:%S").timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def exposure_text(exposure, fnumber, iso, focal):
    parts = []
    t = _number(exposure)
    if t:
        parts.append(f"1/{round(1 / t)} s" if t < 1 else f"{t:g} s")
    f = _number(fnumber)
    if f:
        parts.append(f"f/{f:.1f}".replace(".0", ""))
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    i = _number(iso)
    if i:
        parts.append(f"ISO {int(i)}")
    mm = _number(focal)
    if mm:
        parts.append(f"{mm:g} mm")
    return " · ".join(parts) or None


def _degrees(dms):
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return d + m / 60 + s / 3600


def gps_text(gps) -> str | None:
    """``35.65858° N, 139.74543° E`` — the coordinates as stored, nothing
    looked up and nothing sent anywhere."""
    if not gps:
        return None
    lat, lon = _degrees(gps.get(2)), _degrees(gps.get(4))
    if lat is None or lon is None:
        return None
    ns = clean(gps.get(1)) or "N"
    ew = clean(gps.get(3)) or "E"
    return f"{lat:.5f}° {ns}, {lon:.5f}° {ew}"


# --- audio and video ----------------------------------------------------------------

_warned = []


def read_av(path) -> dict:
    try:
        from pymediainfo import MediaInfo
    except ImportError:
        return {}
    try:
        info = MediaInfo.parse(str(path))
    except Exception as e:  # noqa: BLE001 — no library, or a file it cannot read
        if not _warned:
            _warned.append(True)
            logger.warning(f"media-info: MediaInfo could not read {path}: {e}")
        return {}
    general = next((t for t in info.tracks if t.track_type == "General"), None)
    video = next((t for t in info.tracks if t.track_type == "Video"), None)
    audio = next((t for t in info.tracks if t.track_type == "Audio"), None)
    if general is None or (video is None and audio is None):
        return {}
    out = {}
    duration = _number(general.duration) or _number(getattr(video or audio, "duration", None))
    if duration:
        out["duration"] = duration / 1000.0
    for key, attr in (("title", "title"), ("artist", "performer"),
                      ("album", "album"), ("genre", "genre")):
        text = clean(getattr(general, attr, None))
        if text:
            out[key] = text
    year = clean(general.recorded_date) or clean(getattr(general, "original_released_date", None))
    if year:
        out["year"] = year[:4] if year[:4].isdigit() else year
    position = clean(general.track_name_position)
    if position:
        total = clean(general.track_name_total)
        out["track"] = f"{position}/{total}" if total else position
    rate = _number(general.overall_bit_rate)
    if rate:
        out["bitrate"] = f"{round(rate / 1000)} kb/s"
    if video is not None:
        width, height = _number(video.width), _number(video.height)
        if width and height:
            if str(getattr(video, "rotation", "") or "").split(".")[0] in ("90", "270", "-90"):
                width, height = height, width
            out["dimensions"] = dimensions(width, height)
        parts = [clean(video.format)]
        fps = _number(video.frame_rate)
        if fps:
            parts.append(f"{fps:.3f}".rstrip("0").rstrip(".") + " fps")
        out["video"] = " · ".join(p for p in parts if p) or None
        when = media_time(general.encoded_date or general.tagged_date
                          or getattr(general, "recorded_date", None))
        if when is not None:
            out["date"] = when
    if audio is not None:
        parts = [clean(audio.format)]
        hz = _number(audio.sampling_rate)
        if hz:
            parts.append(f"{hz / 1000:g} kHz")
        channels = _number(audio.channel_s)
        if channels:
            parts.append({1: "mono", 2: "stereo"}.get(int(channels), f"{int(channels)} ch"))
        out["audio"] = " · ".join(p for p in parts if p) or None
    return {k: v for k, v in out.items() if v is not None}


def media_time(value):
    """MediaInfo's ``2024-03-15 14:30:22 UTC`` (or its older ``UTC 2024-…``)
    as a timestamp."""
    text = clean(value)
    if not text:
        return None
    utc = "UTC" in text
    text = text.replace("UTC", "").strip()
    try:
        when = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if utc:
        from datetime import timezone
        when = when.replace(tzinfo=timezone.utc)
    try:
        return when.timestamp()
    except (OverflowError, OSError):
        return None
