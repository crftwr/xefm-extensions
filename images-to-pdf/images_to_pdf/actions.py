"""The action images-to-pdf contributes. The image work is in plain functions
(see logic.py) so it can be tested without XeFM."""

import pathlib

from xefm.user_api import md_escape

from images_to_pdf.logic import (
    default_name, folder_label, is_local, load_page, pdf_name, write_pdf)

TITLE = "Images to PDF"


def combine(ctx):
    """Combine the selected images into one PDF, one image per page.

    Takes the selected files in the pane's order — or the file under the
    cursor — and asks for the PDF's name. The PDF is written to the other
    pane's folder. Photos are turned upright by their EXIF orientation, and
    each page is the image's own size. Files that are not images are skipped
    and listed. Images can come from anywhere XeFM reads (archives, SSH, S3);
    the destination must be a local folder."""
    entries = [e for e in (ctx.pane.selected() or [ctx.pane.focused])
               if e is not None and e.name != ".." and not e.is_dir]
    if not entries:
        ctx.message(f"{TITLE}: no files selected")
        return
    dest_pane = ctx.other.name             # "left" / "right", for the callback
    dest = ctx.other.path
    if not is_local(dest):
        ctx.message(f"{TITLE}: the other pane must show a local folder "
                    f"(it shows {dest})")
        return
    sources = [(e.name, e.path) for e in entries]
    default = default_name([(e.stem, e.suffix) for e in entries])

    def accepted(text):
        name = pdf_name(text, default)
        if name is None:
            ctx.message(f"{TITLE}: not a file name: {text!r}")
            return
        target = pathlib.Path(str(dest)) / name
        if target.exists():
            ctx.confirm(f"{name} exists in {dest}. Replace it?",
                        title=TITLE,
                        on_result=lambda yes: yes and _run(ctx, sources, target,
                                                           dest_pane))
        else:
            _run(ctx, sources, target, dest_pane)

    ctx.input("PDF name", default,
              title=f"{TITLE}: {len(sources)} file(s) → {folder_label(dest)}",
              on_accept=accepted)


def _run(ctx, sources, target, dest_pane):
    def work(job):                      # worker thread: touch only `job`
        pages, skipped = [], []
        for i, (name, path) in enumerate(sources):
            job.checkpoint()
            job.progress(i, len(sources), detail=name)
            try:
                with path.open("rb") as stream:
                    pages.append(load_page(stream))
            except Exception as exc:
                job.checkpoint()        # a cancel mid-file ends the task here
                skipped.append((name, _reason(exc)))
        job.checkpoint()
        if pages:
            job.progress(len(sources), len(sources), detail=f"Writing {target.name}")
            write_pdf(pages, target)
        return len(pages), skipped

    def done(ctx, outcome):             # UI thread, with a fresh ctx
        if outcome.ok:
            count, skipped = outcome.value
            if count:
                pane = getattr(ctx, dest_pane)
                pane.cd(pane.path, focus_name=target.name)
                ctx.message(f"{TITLE}: {target.name} — {count} page(s)")
            if skipped:
                ctx.show_markdown(TITLE, _skipped_markdown(count, target, skipped))
        elif outcome.status == "cancelled":
            ctx.message(f"{TITLE}: cancelled — no PDF written")

    ctx.run_task(f"{TITLE}: {target.name}", work, on_done=done)


def _reason(exc):
    if type(exc).__name__ == "UnidentifiedImageError":
        return "not an image Pillow can read"
    return getattr(exc, "strerror", None) or str(exc) or type(exc).__name__


def _skipped_markdown(count, target, skipped):
    head = (f"Wrote **{md_escape(target.name)}** with {count} page(s)."
            if count else "No PDF was written: none of the files is an image.")
    return head + "\n\n**Skipped**\n\n" + "\n".join(
        f"- {md_escape(name)}: {md_escape(reason)}" for name, reason in skipped)
