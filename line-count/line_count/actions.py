"""The action line-count contributes. The counting is in plain functions (see
logic.py) so it can be tested without XeFM."""

import time

from xefm.user_api import md_code_block, md_escape

from line_count.logic import (
    Binary, count_stream, error_text, result_markdown, walk)

TITLE = "Count Lines"


def count_lines(ctx):
    """Count lines, words and characters of the selected files.

    Counts the selected files — or the file under the cursor when nothing is
    selected. A selected folder is counted with everything in it, skipping
    hidden files and folders, so one key answers "how big is this source
    tree". Binary files are skipped and listed. Works on remote and
    in-archive files too.

    The result is a table, longest file first, with the totals ready to
    copy."""
    entries = ctx.pane.selected() or [ctx.pane.focused]
    roots = [(e.name, e.path) for e in entries
             if e is not None and e.name != ".."]
    if not roots:
        ctx.message(f"{TITLE}: nothing to count")
        return

    def work(job):                      # worker thread: touch only `job`
        job.progress(0, 0, detail="Listing files…")
        files = []
        for name, path in roots:
            for item in walk(path, name, job.cancelled):
                job.checkpoint()
                files.append(item)
        results, binary, failed = [], [], []
        for i, (name, path) in enumerate(files):
            job.checkpoint()
            job.progress(i, len(files), detail=name)
            try:
                size = path.stat().st_size
            except Exception:
                size = 0
            shown = [time.monotonic()]

            def on_read(read, size=size):
                now = time.monotonic()
                if size and now - shown[0] >= 0.25:
                    shown[0] = now
                    job.item_progress(read, size)

            try:
                with path.open("rb") as stream:
                    counts = count_stream(stream, job.cancelled, on_read)
                job.checkpoint()        # a cancel mid-file ends the task here
                results.append((name, counts))
            except Binary:
                binary.append(name)
            except Exception as exc:
                job.checkpoint()
                failed.append((name, error_text(exc)))
        job.progress(len(files), len(files))
        return results, binary, failed

    def done(ctx, outcome):             # UI thread, with a fresh ctx
        if outcome.ok:
            results, binary, failed = outcome.value
            ctx.show_markdown(TITLE, result_markdown(
                results, binary, failed,
                md_escape=md_escape, md_code_block=md_code_block))
        elif outcome.status == "cancelled":
            ctx.message(f"{TITLE}: cancelled")

    ctx.run_task(TITLE, work, on_done=done, read_only=True)
