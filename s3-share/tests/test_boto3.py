"""presign_all against the real boto3 with fake credentials: the location
lookup fails (no network, or AWS refusing the fake key), so the session's
region is used, and the URL must be signed for that region's host. Signing
itself needs no network. Skipped where boto3 is not installed."""

import urllib.parse

import pytest

boto3 = pytest.importorskip("boto3")
from s3_share.logic import (  # noqa: E402
    client_config, presign_all, uses_temporary_credentials)


@pytest.fixture
def session(monkeypatch, tmp_path):
    for name in ("AWS_PROFILE", "AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLEEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "token")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    return boto3.session.Session()


def test_real_boto3_signs_for_the_regional_host(session):
    config = client_config(timeout=1)
    links, guessed = presign_all(session, [("my-bucket", "dir/a b.txt")], 86400,
                                 client_config=config)
    assert guessed == ["my-bucket"]
    url = urllib.parse.urlparse(links[0][2])
    query = urllib.parse.parse_qs(url.query)
    assert url.netloc == "my-bucket.s3.ap-northeast-1.amazonaws.com"
    assert url.path == "/dir/a%20b.txt"
    assert query["X-Amz-Expires"] == ["86400"]
    assert query["X-Amz-Credential"][0].split("/")[2] == "ap-northeast-1"
    assert "X-Amz-Security-Token" in query
    assert uses_temporary_credentials(session)
