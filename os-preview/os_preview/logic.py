"""Plain functions with no XeFM in them — what the tests exercise.

Each OS has its own preview, and each is started its own way. A platform is
one row in :data:`PREVIEWERS`: a function that turns the paths into the
command to run. macOS is the only row so far (crftwr/xefm discussion 891).
"""

import importlib.util
import os

#: The most files handed to the preview at once. A command line has a size
#: limit, and nobody steps through more than this with the arrow keys.
MAX_ITEMS = 500

#: The helper that shows the Quick Look panel, run as a script by XeFM's
#: Python (see quicklook_helper.py for why it is a process of its own).
QUICKLOOK_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "quicklook_helper.py")


def is_local(path_text):
    """XeFM prints a local path as a plain path and anything else (an archive,
    SSH, S3) as a URI. The OS preview reads files from the disk only."""
    return "://" not in path_text


def targets(entries):
    """``(paths, skipped)`` for the entries to preview: the local ones as
    text, at most :data:`MAX_ITEMS`, and how many were left out because they
    are not on the local disk. ``..`` is never previewed."""
    paths, skipped = [], 0
    for entry in entries:
        if entry is None or entry.name == "..":
            continue
        text = str(entry.path)
        if is_local(text):
            paths.append(text)
        else:
            skipped += 1
    return paths[:MAX_ITEMS], skipped


#: What the helper imports. In the app bundle XeFM's interpreter does not find
#: these by itself when it runs a script, so the helper is told where XeFM
#: has them.
PYOBJC_MODULES = ("objc", "Foundation", "AppKit", "Quartz")


def module_dirs(names, find_spec=importlib.util.find_spec):
    """The folders the top-level packages ``names`` are imported from, each
    once, without importing any of them. A package that is not installed adds
    nothing."""
    dirs = []
    for name in names:
        try:
            spec = find_spec(name)
        except (ImportError, ValueError):
            spec = None
        origin = getattr(spec, "origin", None)
        if not origin:
            continue
        # <dir>/<name>/__init__.py, or <dir>/<name>.py
        parent = os.path.dirname(origin)
        if os.path.basename(origin).startswith("__init__."):
            parent = os.path.dirname(parent)
        if parent not in dirs:
            dirs.append(parent)
    return dirs


def quicklook_command(paths, *, python, find_spec=importlib.util.find_spec):
    """macOS: the helper, run by ``python``, with PyObjC on its path. Without
    PyObjC the helper still runs, and falls back to ``qlmanage``."""
    dirs = module_dirs(PYOBJC_MODULES, find_spec)
    env = {"PYTHONPATH": os.pathsep.join(dirs)} if dirs else {}
    return [python, QUICKLOOK_HELPER, *paths], env


#: ``sys.platform`` -> the function that builds ``(command, env)``.
PREVIEWERS = {
    "darwin": quicklook_command,
}

#: What the preview is called on each platform, for messages.
NAMES = {
    "darwin": "Quick Look",
}


def preview_command(platform, paths, *, python):
    """``(command, env)`` to show ``paths`` in this platform's preview, or
    ``None`` where there is none yet."""
    build = PREVIEWERS.get(platform)
    if build is None:
        return None
    return build(paths, python=python)


def preview_name(platform):
    return NAMES.get(platform, "OS Preview")
