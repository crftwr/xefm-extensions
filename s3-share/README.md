# S3 Share

An [XeFM](https://github.com/crftwr/xefm) extension: copy a time-limited
HTTPS link (a *presigned URL*) to an object on S3, for sharing a file with
someone who has no AWS access.

## Install

Needs XeFM 1.9.0 or later. The desktop app and the terminal app share
`~/.xefm`, so either way below installs it for both.

**With the `xefm` command** (pip, pipx, uv or the Homebrew formula):

```bash
xefm ext install github:crftwr/xefm-extensions/s3-share
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

**In the desktop app** (macOS, Windows), which has no `xefm` command:

1. Download
   [main.zip](https://github.com/crftwr/xefm-extensions/archive/refs/heads/main.zip).
   Once 0.1.0 is released, its tag's zip,
   [s3-share-v0.1.0.zip](https://github.com/crftwr/xefm-extensions/archive/refs/tags/s3-share-v0.1.0.zip),
   gives that exact version.
2. Extract it: put the cursor on the zip and choose **File ▸ Extract
   Archive…** (XeFM extracts into the other pane's folder), or use Finder /
   Explorer. The zip itself cannot be installed, because the package is in a
   subfolder.
3. Open the extracted folders until you see `s3-share`, put the cursor on it
   and choose **Tools ▸ Advanced ▸ Install Extension…**.
4. XeFM lists what the package adds: the `s3-share.presign` action and its
   context-menu item. Choose **Install** (the dialog starts on Cancel). XeFM
   reloads its configuration.

It uses boto3, which XeFM already includes for its S3 support.

## Use

1. Open an `s3://bucket/…` folder in XeFM and put the cursor on a file — or
   select several files to get one link per line.
2. Choose **Copy Presigned URL…** in the row's context menu, or
   `s3-share.presign` in the command palette.
3. Pick how long the link works: **1 hour**, **1 day** or **7 days** (the
   longest S3 allows). The last choice is offered first.
4. The link is copied to the clipboard and shown, with the time it expires.

Things to know:

- The link is signed with the same AWS credentials XeFM uses (the standard
  chain: environment variables, `AWS_PROFILE`, `~/.aws`, an IAM role).
  `AWS_ENDPOINT_URL` is honoured, for S3-compatible storage.
- With **temporary credentials** — SSO, an assumed role, an instance profile —
  the link stops working when those credentials expire, which can be sooner
  than the lifetime you picked. The result says so when this applies.
- The link is signed for the bucket's own region. That needs permission to
  read the bucket's location (`s3:GetBucketLocation`); without it the link is
  signed for your session's region, and the result says so.
- Signing does not check anything: if you cannot read the object, neither
  can whoever opens the link.
- Anything that is not a file on S3 (a local file, a folder, a bucket) is
  ignored.

There is no default key. To bind one, add it to `KEY_BINDINGS` in
`~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    's3-share.presign': ['Ctrl-Shift-U'],
}
```

## Develop

```bash
xefm ext check s3-share
cd s3-share && python -m pytest tests
```

`tests/test_logic.py` needs nothing; `tests/test_actions.py` needs XeFM
importable; `tests/test_boto3.py` signs with the real boto3 and fake
credentials (no AWS account or network needed).

This package uses only XeFM's public API (`xefm.user_api.__all__`), much of
which is still Preview (`API_VERSION` 0) and may change.
