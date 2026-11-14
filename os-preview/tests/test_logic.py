"""The plain functions: which entries are previewed and what is run."""

import os
import subprocess
import sys
from types import SimpleNamespace

from os_preview import logic, quicklook_helper


def entry(name, path=None):
    return SimpleNamespace(name=name, path=path or f"/home/me/{name}")


def test_targets_keep_local_entries_in_order():
    paths, skipped = logic.targets([entry("a.mov"), entry("b.docx")])
    assert paths == ["/home/me/a.mov", "/home/me/b.docx"]
    assert skipped == 0


def test_targets_leave_out_remote_and_archive_entries():
    paths, skipped = logic.targets([
        entry("a.mov"),
        entry("b.mov", "ssh://host/b.mov"),
        entry("c.mov", "archive:///home/me/x.zip#c.mov")])
    assert paths == ["/home/me/a.mov"]
    assert skipped == 2


def test_targets_skip_the_parent_row_and_an_empty_pane():
    assert logic.targets([entry("..", "/home")]) == ([], 0)
    assert logic.targets([None]) == ([], 0)


def test_targets_are_capped():
    entries = [entry(f"{i}.jpg") for i in range(logic.MAX_ITEMS + 10)]
    paths, _ = logic.targets(entries)
    assert len(paths) == logic.MAX_ITEMS
    assert paths[0] == "/home/me/0.jpg"


def fake_find_spec(found):
    def find_spec(name):
        origin = found.get(name)
        return SimpleNamespace(origin=origin) if origin else None
    return find_spec


def test_module_dirs_name_each_folder_once():
    find_spec = fake_find_spec({
        "objc": "/site/objc/__init__.py",
        "AppKit": "/site/AppKit/__init__.py",
        "Quartz": "/bundle/python_packages/Quartz/__init__.py",
        "single": "/other/single.py"})
    assert logic.module_dirs(["objc", "AppKit", "Quartz", "single", "gone"],
                             find_spec) == ["/site", "/bundle/python_packages",
                                            "/other"]


def test_macos_runs_the_helper_with_pyobjc_on_its_path():
    find_spec = fake_find_spec({name: f"/site/{name}/__init__.py"
                                for name in logic.PYOBJC_MODULES})
    command, env = logic.quicklook_command(["/a b.mov", "/c.mp3"], python="/py",
                                           find_spec=find_spec)
    assert command == ["/py", logic.QUICKLOOK_HELPER, "/a b.mov", "/c.mp3"]
    assert os.path.isfile(logic.QUICKLOOK_HELPER)
    assert env == {"PYTHONPATH": "/site"}


def test_macos_without_pyobjc_sets_no_path():
    command, env = logic.quicklook_command(["/a.mov"], python="/py",
                                           find_spec=fake_find_spec({}))
    assert command[:2] == ["/py", logic.QUICKLOOK_HELPER]
    assert env == {}


def test_other_platforms_have_no_preview_yet():
    assert logic.preview_command("win32", ["x"], python="py") is None
    assert logic.preview_name("darwin") == "Quick Look"
    assert logic.preview_name("win32") == "OS Preview"


def test_helper_drops_missing_files(tmp_path, capsys):
    there = tmp_path / "a.txt"
    there.write_text("x")
    assert quicklook_helper.existing([str(there), str(tmp_path / "gone")]) \
        == [str(there)]
    assert quicklook_helper.main([str(tmp_path / "gone")]) == 2
    assert "none of the files exist" in capsys.readouterr().err


def test_system_log_is_dropped_but_python_errors_are_kept():
    # What AppKit writes goes to fd 2 directly; sys.stderr is Python's own.
    code = ("import os, sys; from os_preview import quicklook_helper as q; "
            "q.quiet_system_log(); os.write(2, b'IMK noise\\n'); "
            "sys.stderr.write('helper message\\n')")
    run = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=os.path.dirname(os.path.dirname(
                             os.path.abspath(__file__))))
    assert run.returncode == 0
    assert "IMK noise" not in run.stderr
    assert "helper message" in run.stderr
