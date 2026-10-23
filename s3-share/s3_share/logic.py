"""Plain functions — what the tests exercise. Nothing here imports XeFM, and
boto3 is only touched through the ``session`` passed in, so the tests can hand
in a fake one."""

import time

#: (label, seconds). Seven days is the longest a SigV4 signature can last.
LIFETIMES = [("1 hour", 3600), ("1 day", 86400), ("7 days", 7 * 86400)]


def client_config(timeout=10):
    """The botocore config the action signs with.

    Virtual-host addressing makes boto3 sign for the bucket's regional host
    (``bucket.s3.<region>.amazonaws.com``). The default signs for the global
    ``s3.amazonaws.com``, which a bucket outside us-east-1 may answer with a
    redirect that a presigned link cannot follow. Names that cannot be a host
    (dots, capitals) still get the regional path style, and
    ``AWS_ENDPOINT_URL`` is honoured."""
    from botocore.config import Config
    return Config(signature_version="s3v4", s3={"addressing_style": "virtual"},
                  connect_timeout=timeout, read_timeout=2 * timeout,
                  retries={"max_attempts": 2})


def parse_s3_uri(text):
    """``(bucket, key)`` for an ``s3://bucket/key`` path as XeFM prints it, or
    ``None`` when it is not an object on S3 (another scheme, a bucket, a
    "folder" key ending in ``/``)."""
    if not text.startswith("s3://"):
        return None
    bucket, _, key = text[5:].partition("/")
    if not bucket or not key or key.endswith("/"):
        return None
    return bucket, key


def bucket_region(location):
    """A bucket's region from ``get_bucket_location``'s answer: S3 says
    nothing (``None``/``""``) for us-east-1, and ``EU`` for the oldest
    eu-west-1 buckets."""
    if not location:
        return "us-east-1"
    if location == "EU":
        return "eu-west-1"
    return location


def ordered_lifetimes(last_seconds):
    """LIFETIMES with the last one used first, so Enter repeats it."""
    return sorted(LIFETIMES, key=lambda item: item[1] != last_seconds)


def uses_temporary_credentials(session):
    """True when the session's credentials carry a session token: SSO, an
    assumed role, an instance profile. A link signed with them stops working
    when they expire, whatever lifetime was asked for."""
    creds = session.get_credentials()
    if creds is None:
        return False
    frozen = creds.get_frozen_credentials()
    return bool(getattr(frozen, "token", None))


def presign_all(session, objects, seconds, *, client_config=None,
                checkpoint=lambda: None):
    """``[(bucket, key, url)]`` for ``objects`` (``[(bucket, key)]``), each
    signed for ``seconds`` with a client in its bucket's region — a link
    signed for the wrong region fails when it is opened. Returns the links
    and the buckets whose region could not be read (signed with the session's
    own region instead)."""
    regions, guessed, clients, links = {}, [], {}, []
    for bucket, key in objects:
        checkpoint()
        if bucket not in regions:
            try:
                location = session.client("s3", config=client_config) \
                    .get_bucket_location(Bucket=bucket).get("LocationConstraint")
                regions[bucket] = bucket_region(location)
            except Exception:
                regions[bucket] = None      # the session's region
                guessed.append(bucket)
        region = regions[bucket]
        if region not in clients:
            clients[region] = session.client("s3", region_name=region,
                                             config=client_config)
        url = clients[region].generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key},
            ExpiresIn=seconds)
        links.append((bucket, key, url))
    return links, guessed


def expiry_text(seconds, now=None):
    """When the links stop working, in local time."""
    when = (time.time() if now is None else now) + seconds
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(when))


def result_markdown(links, label, seconds, *, temporary, guessed,
                    md_escape, md_code_block, now=None):
    parts = []
    if links:
        parts.append(f"Valid for **{label}**, until {expiry_text(seconds, now)}. "
                     "Copied to the clipboard.")
        parts.append(md_code_block("\n".join(url for _, _, url in links)))
        if len(links) > 1:
            parts.append("\n".join(f"{i}. {md_escape(key.rsplit('/', 1)[-1])}"
                                   for i, (_, key, _) in enumerate(links, 1)))
    if temporary:
        parts.append("**Signed with temporary credentials** (SSO, an assumed "
                     "role or an instance profile): the link stops working when "
                     "they expire, which may be sooner.")
    if guessed:
        parts.append("**Region not readable** for "
                     + ", ".join(md_escape(b) for b in guessed)
                     + ": signed with the session's region. If the link fails, "
                     "check that region or permission to read the bucket location.")
    parts.append("The link is not checked: if you cannot read the object, "
                 "neither can whoever opens it.")
    return "\n\n".join(parts)
