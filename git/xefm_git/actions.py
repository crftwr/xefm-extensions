"""The actions: the changed files as one list, a revision as a folder, a file
beside an older version of itself, its history, and the Git tool that does the
writing. Every one only reads the repository."""

import os
import posixpath
import shutil

from xefm.user_api import extension

from xefm_git import repo


def _where(ctx):
    """``(top, rev, prefix)`` for the active pane: a local folder in a working
    tree (``rev`` None), or a ``git://`` revision folder. None elsewhere."""
    path = ctx.pane.path
    parts = repo.split_uri(str(path))
    if parts is not None:
        top, rev, key = parts
        return top, rev, key + "/" if key else ""
    if getattr(path, "scheme", "file") != "file":
        return None
    tree = repo.work_tree(path)
    return (tree.top, None, tree.prefix) if tree is not None else None


def _not_here(ctx, what):
    ctx.message(f"Git: {what} needs a folder inside a Git working tree")


def _focused_file(ctx, what):
    """The file under the cursor, or None (and a message)."""
    entry = ctx.pane.focused
    if entry is None or entry.is_dir:
        ctx.message(f"Git: {what} works on a file — put the cursor on one")
        return None
    return entry


def _in_repo(entry):
    """``(top, key)`` for a local file in a working tree, from the file's own
    folder — not the pane's, which a flat list (Changed Files, a search)
    roots higher up. None outside a working tree."""
    path = entry.path
    if getattr(path, "scheme", "file") != "file":
        return None
    tree = repo.work_tree(path.parent)
    return (tree.top, tree.prefix + path.name) if tree is not None else None


def changed(ctx):
    """Every changed and untracked file of the repository, as one list."""
    where = _where(ctx)
    if where is None:
        _not_here(ctx, "Changed Files")
        return
    top = where[0]

    def work(job):
        return [os.path.join(top, *path.rstrip("/").split("/"))
                for _, path in repo.status(top)]

    def done(ctx, outcome):
        if not outcome.ok:
            return
        if not outcome.value:
            ctx.message(f"Git: no changes in {top}")
            return
        ctx.pane.open_list(outcome.value, title=f"Git changes — {posixpath.basename(top)}")

    ctx.run_task("Git: changed files", work, on_done=done, read_only=True)


def browse(ctx):
    """Open a revision — HEAD, a branch, a tag or a recent commit — as a
    read-only folder, at the folder you are in."""
    where = _where(ctx)
    if where is None:
        _not_here(ctx, "Browse Revision")
        return
    top, _, prefix = where
    try:
        refs = repo.refs(top)
    except repo.GitError as e:
        ctx.message(f"Git: {e}")
        return
    focused = ctx.pane.focused
    focus = focused.path.name if focused is not None else None

    def chosen(index):
        if index is None:
            return
        _open_revision(ctx, top, refs[index].rev, prefix, focus)

    ctx.choose("Browse Revision", [r.label for r in refs], type="filter",
               on_result=chosen)


def _open_revision(ctx, top, rev, prefix, focus=None):
    """Go to ``prefix`` in ``rev``, or to the revision's top where it has no
    such folder."""
    from xefm_git.tree import GitPathImpl
    target = repo.uri(top, rev, prefix)
    if prefix and not GitPathImpl(target).is_dir():
        target, focus = repo.uri(top, rev), None
    ctx.pane.cd(target, focus_name=focus)


def diff_head(ctx):
    """Compare the file under the cursor with its HEAD version. In a revision
    folder, compare that revision's file with the working tree's."""
    entry = _focused_file(ctx, "Compare with HEAD")
    if entry is None:
        return
    parts = repo.split_uri(str(entry.path))
    if parts is not None:
        top, rev, key = parts
        working = os.path.join(top, *key.split("/"))
        if not os.path.isfile(working):
            ctx.message(f"Git: {key} is not in the working tree")
            return
        ctx.diff(entry, working, left_title=f"{rev}: {key}", right_title="Working tree")
        return
    found = _in_repo(entry)
    if found is None:
        _not_here(ctx, "Compare with HEAD")
        return
    top, key = found
    if not repo.has_object(top, "HEAD", key):
        ctx.message(f"Git: {key} is not in HEAD — a new file")
        return
    ctx.diff(repo.uri(top, "HEAD", key), entry, left_title=f"HEAD: {key}",
             right_title="Working tree")


COMPARE_WORKING, COMPARE_PARENT, OPEN_FOLDER = range(3)
CHOICES = ["Compare with the working file", "Compare with the version before",
           "Open this revision's folder"]


def log(ctx):
    """The commits that changed the file under the cursor; pick one to compare
    it or to open its folder."""
    entry = _focused_file(ctx, "File History")
    if entry is None:
        return
    parts = repo.split_uri(str(entry.path))
    if parts is not None:
        top, _, key = parts
    else:
        found = _in_repo(entry)
        if found is None:
            _not_here(ctx, "File History")
            return
        top, key = found
    limit = extension(__name__).settings.LOG_LIMIT

    def work(job):
        return repo.history(top, key, limit)

    def done(ctx, outcome):
        if not outcome.ok:
            return
        commits = outcome.value
        if not commits:
            ctx.message(f"Git: no commits change {key}")
            return
        ctx.choose(f"History of {posixpath.basename(key)}",
                   [c.label for c in commits], type="filter",
                   on_result=lambda i: i is not None and _commit_chosen(ctx, top, key, commits[i]))

    ctx.run_task("Git: file history", work, on_done=done, read_only=True)


def _commit_chosen(ctx, top, key, commit):
    def act(choice):
        if choice == COMPARE_WORKING:
            working = os.path.join(top, *key.split("/"))
            if not os.path.isfile(working):
                ctx.message(f"Git: {key} is not in the working tree")
                return
            ctx.diff(repo.uri(top, commit.id, commit.path), working,
                     left_title=f"{commit.short}: {commit.path}", right_title="Working tree")
        elif choice == COMPARE_PARENT:
            if commit.old_path is None:
                ctx.message(f"Git: {commit.short} added {commit.path} — there is no version before")
                return
            ctx.diff(repo.uri(top, f"{commit.id}^", commit.old_path),
                     repo.uri(top, commit.id, commit.path),
                     left_title=f"{commit.short}^: {commit.old_path}",
                     right_title=f"{commit.short}: {commit.path}")
        elif choice == OPEN_FOLDER:
            folder, _, name = commit.path.rpartition("/")
            _open_revision(ctx, top, commit.id, folder, name)

    ctx.choose(f"{commit.short}  {commit.subject}", CHOICES, on_result=act)


def open_tool(ctx):
    """Start your Git tool (GitConfig.TOOL) in the repository — where adding,
    committing and switching branches happen."""
    where = _where(ctx)
    if where is None:
        _not_here(ctx, "Open Git Tool")
        return
    settings = extension(__name__).settings
    command = settings.TOOL
    program = command[0] if isinstance(command, (list, tuple)) else str(command).split()[0]
    if shutil.which(program) is None:
        ctx.message(f"Git: {program} is not on PATH — set TOOL in GitConfig "
                    f"(xefm ext settings git)")
        return
    ctx.run_program(command, terminal=bool(settings.TOOL_TERMINAL), cwd=where[0])
    ctx.pane.refresh()
