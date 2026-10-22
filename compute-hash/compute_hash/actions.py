"""The actions compute-hash contributes. Each takes the action context ``ctx``;
the work itself is in plain functions (see logic.py) so it can be tested
without XeFM."""

import time

from xefm.user_api import extension, md_code_block, md_escape

from compute_hash.logic import (
    checksum_line, digest_stream, error_text, ordered_algorithms)

TITLE = "Compute Hash"
STATE_KEY = "algorithm"


def compute(ctx):
    """Compute the hash of the selected files.

    Asks for an algorithm (MD5, SHA-1, SHA-256, SHA-512 or BLAKE2b; the last
    one used comes first), hashes the selected files — or the file under the
    cursor when nothing is selected — and shows the digests in sha256sum form,
    ready to copy. Directories are skipped. Works on remote and in-archive
    files too."""
    entries = ctx.pane.selected() or [ctx.pane.focused]
    targets = [(e.name, e.path) for e in entries
               if e is not None and e.name != ".." and not e.is_dir]
    if not targets:
        ctx.message(f"{TITLE}: no files to hash")
        return

    algorithms = ordered_algorithms(extension(__name__).state.get(STATE_KEY))

    def chosen(index):
        if index is None:
            return
        label, algorithm = algorithms[index]
        extension(__name__).state.set(STATE_KEY, algorithm)
        _run(ctx, targets, label, algorithm)

    ctx.choose(f"{TITLE}: Algorithm", [label for label, _ in algorithms],
               type="filter", on_result=chosen)


def _run(ctx, targets, label, algorithm):
    def work(job):                      # worker thread: touch only `job`
        results = []
        for i, (name, path) in enumerate(targets):
            job.checkpoint()
            job.progress(i, len(targets), detail=name)
            try:
                size = path.stat().st_size
            except Exception:
                size = 0                # unknown: the open below says why
            # The bar counts files; a second bar shows how far into this one,
            # updated a few times a second, so one large file still moves.
            shown = [time.monotonic()]

            def on_read(read, size=size):
                now = time.monotonic()
                if size and now - shown[0] >= 0.25:
                    shown[0] = now
                    job.item_progress(read, size)

            try:
                with path.open("rb") as stream:
                    results.append((name, digest_stream(
                        stream, algorithm, job.cancelled, on_read), None))
            except Exception as exc:
                job.checkpoint()        # a cancel mid-file ends the task here
                results.append((name, None, error_text(exc)))
        job.progress(len(targets), len(targets))
        return results

    def done(ctx, outcome):             # UI thread, with a fresh ctx
        if outcome.ok:
            ctx.show_markdown(TITLE, result_markdown(label, outcome.value))
        elif outcome.status == "cancelled":
            ctx.message(f"{TITLE}: cancelled")

    ctx.run_task(f"{TITLE} ({label})", work, on_done=done, read_only=True)


def result_markdown(label, results):
    """The result dialog's Markdown: the digests as one code block, whose Copy
    button gives text ``sha256sum -c`` accepts, then any files that could not
    be read. Both in the order the files were given."""
    lines = [checksum_line(digest, name)
             for name, digest, error in results if error is None]
    failed = [(name, error) for name, _, error in results if error is not None]
    parts = [f"**{label}**"]
    if lines:
        parts.append(md_code_block("\n".join(lines)))
    if failed:
        parts.append("**Could not read**")
        parts.append("\n".join(f"- {md_escape(name)}: {md_escape(error)}"
                               for name, error in failed))
    return "\n\n".join(parts)
