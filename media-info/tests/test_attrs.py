"""media_info.attrs — the providers XeFM calls, and the folder check."""

from pathlib import Path
from types import SimpleNamespace

from media_info import attrs, read

DATA = Path(__file__).parent / "data"


def _entry(path: Path, is_dir=False):
    st = path.stat()
    return SimpleNamespace(name=path.name, path=path, is_dir=is_dir,
                           size=st.st_size, mtime=st.st_mtime)


def test_a_provider_answers_each_entry(tmp_path):
    read.clear_cache()
    (tmp_path / "notes.txt").write_text("hi")
    entries = [_entry(DATA / "tone.m4a"), _entry(DATA / "clip.mp4"),
               _entry(tmp_path / "notes.txt"), _entry(tmp_path, is_dir=True)]
    durations = attrs.duration(tmp_path, entries)
    assert [round(d) if d else d for d in durations] == [2, 1, None, None]
    assert attrs.dimensions(tmp_path, entries) == [None, "64 × 48", None, None]


def test_every_manifest_attribute_has_its_provider():
    import tomllib
    manifest = tomllib.loads((Path(__file__).parent.parent / "xefm-extension.toml")
                             .read_text(encoding="utf-8"))
    for name, spec in manifest["contributes"]["attributes"].items():
        func = getattr(attrs, spec["read"].split(":")[1])
        assert func.__name__ == name.split(".", 1)[1]


def test_a_folder_of_media(tmp_path):
    for name in ("a.jpg", "b.mp3", "c.txt"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "sub").mkdir()
    assert attrs.media_folder(tmp_path)
    for name in ("d.txt", "e.md"):
        (tmp_path / name).write_bytes(b"")
    assert not attrs.media_folder(tmp_path)


def test_not_a_folder_on_the_local_disk():
    assert not attrs.media_folder(SimpleNamespace(scheme="ssh"))
    assert not attrs.media_folder(Path("/no/such/folder"))
