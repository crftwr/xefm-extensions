"""The action s3-share contributes. The S3 work is in plain functions (see
logic.py) so it can be tested without XeFM or AWS."""

from xefm.user_api import extension, md_code_block, md_escape

from s3_share.logic import (
    client_config, ordered_lifetimes, parse_s3_uri, presign_all, result_markdown,
    uses_temporary_credentials)

TITLE = "Presigned URL"
STATE_KEY = "lifetime"


def presign(ctx):
    """Copy a time-limited HTTPS link to the S3 object under the cursor.

    For sharing a file with someone who has no AWS access. Works on files in
    an s3:// pane — the one under the cursor, or each selected file (one link
    per line). Asks how long the link should work (1 hour, 1 day or 7 days),
    signs it with the same AWS credentials XeFM uses, copies it to the
    clipboard and shows it."""
    entries = [e for e in (ctx.pane.selected() or [ctx.pane.focused])
               if e is not None and e.name != ".." and not e.is_dir]
    objects = [parse_s3_uri(str(e.path)) for e in entries]
    objects = [o for o in objects if o]
    if not objects:
        ctx.message(f"{TITLE}: works on files in an s3:// folder")
        return

    lifetimes = ordered_lifetimes(extension(__name__).state.get(STATE_KEY))

    def chosen(index):
        if index is None:
            return
        label, seconds = lifetimes[index]
        extension(__name__).state.set(STATE_KEY, seconds)
        _run(ctx, objects, label, seconds)

    ctx.choose(f"{TITLE}: valid for", [label for label, _ in lifetimes],
               on_result=chosen)


def _run(ctx, objects, label, seconds):
    def work(job):                      # worker thread: touch only `job`
        import boto3
        job.progress(0, len(objects), detail="Signing…")
        session = boto3.session.Session()
        links, guessed = presign_all(session, objects, seconds,
                                     client_config=client_config(),
                                     checkpoint=job.checkpoint)
        return links, guessed, uses_temporary_credentials(session)

    def done(ctx, outcome):             # UI thread, with a fresh ctx
        if outcome.ok:
            links, guessed, temporary = outcome.value
            ctx.copy_text("\n".join(url for _, _, url in links))
            ctx.message(f"{TITLE}: {len(links)} link(s) copied, valid for {label}")
            ctx.show_markdown(TITLE, result_markdown(
                links, label, seconds, temporary=temporary, guessed=guessed,
                md_escape=md_escape, md_code_block=md_code_block))
        elif outcome.status == "failed":
            ctx.message(f"{TITLE}: could not sign — {outcome.error}")
        elif outcome.status == "cancelled":
            ctx.message(f"{TITLE}: cancelled")

    ctx.run_task(TITLE, work, on_done=done, read_only=True)
