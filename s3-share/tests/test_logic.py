from types import SimpleNamespace

import pytest

from s3_share.logic import (
    LIFETIMES, bucket_region, expiry_text, ordered_lifetimes, parse_s3_uri,
    presign_all, result_markdown, uses_temporary_credentials)


def test_parse_s3_uri():
    assert parse_s3_uri("s3://bkt/a/b c.txt") == ("bkt", "a/b c.txt")
    assert parse_s3_uri("s3://bkt") is None
    assert parse_s3_uri("s3://bkt/") is None
    assert parse_s3_uri("s3://bkt/dir/") is None
    assert parse_s3_uri("/home/me/a.txt") is None
    assert parse_s3_uri("ssh://host/a.txt") is None


def test_bucket_region():
    assert bucket_region(None) == "us-east-1"
    assert bucket_region("") == "us-east-1"
    assert bucket_region("EU") == "eu-west-1"
    assert bucket_region("ap-northeast-1") == "ap-northeast-1"


def test_seven_days_is_the_longest():
    assert max(seconds for _, seconds in LIFETIMES) == 7 * 86400


def test_ordered_lifetimes_puts_the_last_first():
    assert ordered_lifetimes(86400)[0] == ("1 day", 86400)
    assert ordered_lifetimes(None) == LIFETIMES


def session_with(token):
    frozen = SimpleNamespace(access_key="AK", secret_key="SK", token=token)
    creds = SimpleNamespace(get_frozen_credentials=lambda: frozen)
    return SimpleNamespace(get_credentials=lambda: creds)


def test_temporary_credentials():
    assert uses_temporary_credentials(session_with("tok"))
    assert not uses_temporary_credentials(session_with(None))
    assert not uses_temporary_credentials(SimpleNamespace(get_credentials=lambda: None))


class FakeSession:
    def __init__(self, locations):
        self.locations, self.clients = locations, []

    def client(self, service, region_name=None, config=None):
        assert service == "s3"
        session = self

        class Client:
            def get_bucket_location(self, Bucket):
                value = session.locations[Bucket]
                if isinstance(value, Exception):
                    raise value
                return {"LocationConstraint": value}

            def generate_presigned_url(self, op, Params, ExpiresIn):
                assert op == "get_object"
                return (f"https://{Params['Bucket']}.{region_name}/"
                        f"{Params['Key']}?X-Amz-Expires={ExpiresIn}")

        self.clients.append(region_name)
        return Client()


def test_presign_signs_in_each_buckets_region():
    session = FakeSession({"tokyo": "ap-northeast-1", "old": None})
    links, guessed = presign_all(
        session, [("tokyo", "a.txt"), ("old", "b.txt"), ("tokyo", "c.txt")], 3600)
    assert [url for _, _, url in links] == [
        "https://tokyo.ap-northeast-1/a.txt?X-Amz-Expires=3600",
        "https://old.us-east-1/b.txt?X-Amz-Expires=3600",
        "https://tokyo.ap-northeast-1/c.txt?X-Amz-Expires=3600",
    ]
    assert guessed == []
    # one location lookup per bucket, one signing client per region
    assert session.clients.count("ap-northeast-1") == 1


def test_unreadable_location_falls_back_to_the_session_region():
    session = FakeSession({"locked": PermissionError("AccessDenied")})
    links, guessed = presign_all(session, [("locked", "x")], 60)
    assert guessed == ["locked"]
    assert links[0][2].startswith("https://locked.None/")


def test_presign_checkpoints_between_objects():
    calls = []
    presign_all(FakeSession({"b": "us-west-2"}), [("b", "1"), ("b", "2")], 60,
                checkpoint=lambda: calls.append(1))
    assert len(calls) == 2


def test_expiry_text_is_local_time():
    assert expiry_text(3600, now=0) == expiry_text(0, now=3600)


def md(links, **kw):
    args = dict(temporary=False, guessed=[], md_escape=lambda s: s,
                md_code_block=lambda s: f"```\n{s}\n```", now=0)
    args.update(kw)
    return result_markdown(links, "1 hour", 3600, **args)


def test_markdown_one_link():
    out = md([("b", "dir/a.txt", "https://u1")])
    assert "```\nhttps://u1\n```" in out
    assert "1 hour" in out and "Copied" in out
    assert "temporary" not in out


def test_markdown_several_links_are_numbered():
    out = md([("b", "x/a.txt", "https://u1"), ("b", "y/b.txt", "https://u2")])
    assert "https://u1\nhttps://u2" in out
    assert "1. a.txt" in out and "2. b.txt" in out


def test_markdown_warnings():
    out = md([("b", "a", "https://u")], temporary=True, guessed=["b"])
    assert "temporary credentials" in out
    assert "Region not readable" in out
