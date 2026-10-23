"""The action unblock-files contributes. The stream handling is in plain
functions (see logic.py) so it can be tested without XeFM — and, since a
path with a colon is an ordinary name on Linux and macOS, without Windows."""

from xefm.user_api import md_escape

from unblock_files.logic import (
    confirm_prompt, error_text, is_local, read_mark, remove_mark,
    result_markdown)

TITLE = "Unblock Files"


def unblock(ctx):
    """Remove the downloaded-from-the-internet mark from the selected files.

    The same as Unblock in Explorer's Properties, or PowerShell's
    Unblock-File, for many files at once: SmartScreen stops warning on launch
    and Office stops opening them in Protected View. Works on the selected
    files, or the file under the cursor; folders are skipped. Before removing
    anything, it says which files carry the mark and where they came from, and
    asks. Local files only."""
    entries = [e for e in (ctx.pane.selected() or [ctx.pane.focused])
               if e is not None and e.name != ".." and not e.is_dir]
    targets = [(e.name, e.path) for e in entries if is_local(str(e.path))]
    if not targets:
        ctx.message(f"{TITLE}: no local files selected")
        return

    def scan(job):                      # worker thread: touch only `job`
        marked, unmarked, failed = [], 0, []
        for i, (name, path) in enumerate(targets):
            job.checkpoint()
            job.progress(i, len(targets), detail=name)
            try:
                mark = read_mark(path)
            except Exception as exc:
                job.checkpoint()
                failed.append((name, error_text(exc)))
                continue
            if mark is None:
                unmarked += 1
            else:
                marked.append(((name, path), mark))
        return marked, unmarked, failed

    def scanned(ctx, outcome):          # UI thread, with a fresh ctx
        if not outcome.ok:
            if outcome.status == "cancelled":
                ctx.message(f"{TITLE}: cancelled")
            return
        marked, unmarked, failed = outcome.value
        if not marked:
            ctx.message(f"{TITLE}: none of the {len(targets)} file(s) is marked")
            if failed:
                ctx.show_markdown(TITLE, result_markdown([], unmarked, failed,
                                                         md_escape=md_escape))
            return
        ctx.confirm(confirm_prompt([(n, m) for (n, _), m in marked]),
                    title=TITLE,
                    on_result=lambda yes: yes and _remove(ctx, marked, unmarked,
                                                          failed))

    ctx.run_task(TITLE, scan, on_done=scanned, read_only=True)


def _remove(ctx, marked, unmarked, failed):
    def work(job):                      # worker thread: touch only `job`
        unblocked, errors = [], list(failed)
        for i, ((name, path), mark) in enumerate(marked):
            job.checkpoint()
            job.progress(i, len(marked), detail=name)
            try:
                remove_mark(path)
                unblocked.append((name, mark))
            except Exception as exc:
                job.checkpoint()
                errors.append((name, error_text(exc)))
        return unblocked, errors

    def done(ctx, outcome):             # UI thread, with a fresh ctx
        if outcome.ok:
            unblocked, errors = outcome.value
            ctx.message(f"{TITLE}: unblocked {len(unblocked)} file(s)")
            ctx.show_markdown(TITLE, result_markdown(unblocked, unmarked, errors,
                                                     md_escape=md_escape))
        elif outcome.status == "cancelled":
            ctx.message(f"{TITLE}: cancelled — files already done stay unblocked")

    ctx.run_task(TITLE, work, on_done=done)
