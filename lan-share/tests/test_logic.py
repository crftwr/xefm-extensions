"""The plain functions: addresses, request paths, ranges, the page. No XeFM,
no socket."""

from lan_share import logic

TOKEN = "AbCdEfGhIjKl"


# --- addresses --------------------------------------------------------------- #

def test_usable_addresses_puts_the_default_route_first_and_drops_the_useless():
    found = logic.usable_addresses(
        "192.168.1.5",
        ["127.0.0.1", "10.0.0.2", "192.168.1.5", "169.254.3.4", "0.0.0.0",
         "fe80::1", "not an address", ""])
    assert found == ["192.168.1.5", "10.0.0.2"]


def test_usable_addresses_without_a_default_route():
    assert logic.usable_addresses(None, ["10.0.0.2"]) == ["10.0.0.2"]
    assert logic.usable_addresses(None, ["127.0.0.1"]) == []


def test_pick_configured_takes_an_address_or_a_prefix():
    addresses = ["10.8.0.3", "192.168.1.5"]
    assert logic.pick_configured(addresses, "192.168.1.5") == "192.168.1.5"
    assert logic.pick_configured(addresses, "192.168.") == "192.168.1.5"
    assert logic.pick_configured(addresses, "172.16.") is None
    assert logic.pick_configured(addresses, "") is None
    # "192.168.1" is no prefix: it would also match 192.168.10.x
    assert logic.pick_configured(addresses, "192.168.1") is None


def test_tokens_differ_and_are_url_safe():
    tokens = {logic.new_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) == 12 and t.replace("-", "").replace("_", "").isalnum()
               for t in tokens)


def test_share_url():
    assert logic.share_url("192.168.1.5", 8000, TOKEN) == \
        f"http://192.168.1.5:8000/{TOKEN}/"


# --- routes ------------------------------------------------------------------ #

def test_the_index_route():
    for target in (f"/{TOKEN}/", f"/{TOKEN}/?x=1"):
        route = logic.parse_route(target, TOKEN)
        assert route.kind == "index" and not route.zip
    assert logic.parse_route(f"/{TOKEN}/?zip", TOKEN).zip


def test_an_item_route_carries_index_segments_and_flags():
    route = logic.parse_route(f"/{TOKEN}/f/2/docs/sub%20dir/a%23b.txt?dl", TOKEN)
    assert (route.kind, route.index, route.segments) == \
        ("item", 2, ["sub dir", "a#b.txt"])
    assert route.download and not route.zip
    folder = logic.parse_route(f"/{TOKEN}/f/0/docs/?zip", TOKEN)
    assert (folder.index, folder.segments, folder.zip) == (0, [], True)


def test_anything_without_the_token_is_no_route():
    for target in ("/", "/favicon.ico", "/wrong/", f"/{TOKEN}", f"/{TOKEN[:-1]}/",
                   f"/x/{TOKEN}/", f"//{TOKEN}/", f"/{TOKEN.lower()}/"):
        assert logic.parse_route(target, TOKEN) is None, target


def test_a_route_cannot_step_out_of_a_folder():
    for below in ("..", "../x", "a/../../x", "%2e%2e", "a/%2e%2e/b", ".",
                  "a%2fb", "a%5cb", "a//b", "%00"):
        target = f"/{TOKEN}/f/0/docs/{below}"
        assert logic.parse_route(target, TOKEN) is None, target


def test_malformed_item_routes_are_no_route():
    for target in (f"/{TOKEN}/f", f"/{TOKEN}/f/0", f"/{TOKEN}/f/x/name",
                   f"/{TOKEN}/f/-1/name", f"/{TOKEN}/g/0/name", f"/{TOKEN}/zip"):
        assert logic.parse_route(target, TOKEN) is None, target


def test_safe_segment_and_hidden_names():
    assert logic.safe_segment("a.txt")
    assert logic.safe_segment(".env")
    assert not logic.safe_segment(".env", include_hidden=False)
    assert logic.safe_segment("..x")
    assert not logic.safe_segment("..")


# --- ranges ------------------------------------------------------------------ #

def test_parse_range():
    size = 1000
    assert logic.parse_range(None, size) is None
    assert logic.parse_range("bytes=0-99", size) == (0, 99)
    assert logic.parse_range("bytes=500-", size) == (500, 999)
    assert logic.parse_range("bytes=-200", size) == (800, 999)
    assert logic.parse_range("bytes=-5000", size) == (0, 999)
    assert logic.parse_range("bytes=990-5000", size) == (990, 999)
    assert logic.parse_range("bytes=1000-", size) == "unsatisfiable"
    assert logic.parse_range("bytes=-0", size) == "unsatisfiable"
    assert logic.parse_range("bytes=0-", 0) == "unsatisfiable"


def test_parse_range_ignores_what_it_does_not_serve():
    for header in ("bytes=0-1,5-6", "items=0-1", "bytes=a-b", "bytes=9-3",
                   "bytes=-", "bytes=5"):
        assert logic.parse_range(header, 1000) is None, header


# --- headers ----------------------------------------------------------------- #

def test_content_type():
    assert logic.content_type("a.mp4") == "video/mp4"
    assert logic.content_type("a.txt") == "text/plain; charset=utf-8"
    assert logic.content_type("a.unknownext") == "application/octet-stream"
    assert logic.content_type("a.tar.gz") == "application/octet-stream"


def test_content_disposition_carries_any_name():
    value = logic.content_disposition('写真 "1".jpg', attachment=True)
    assert value.startswith('attachment; filename="__ _1_.jpg"')
    assert value.endswith("filename*=UTF-8''%E5%86%99%E7%9C%9F%20%221%22.jpg")
    value.encode("latin-1")                     # a header must be
    assert logic.content_disposition("a.txt", attachment=False).startswith("inline;")


def test_item_href_quotes_every_part():
    assert logic.item_href(TOKEN, 1, "my docs", ["a#b", "c?d.txt"]) == \
        f"/{TOKEN}/f/1/my%20docs/a%23b/c%3Fd.txt"
    assert logic.item_href(TOKEN, 0, "docs", folder=True) == f"/{TOKEN}/f/0/docs/"
    href = logic.item_href(TOKEN, 0, "docs", ["a/b"])
    assert logic.parse_route(href, TOKEN) is None       # and a slash stays out


def test_format_size():
    assert logic.format_size(0) == "0 bytes"
    assert logic.format_size(1023) == "1023 bytes"
    assert logic.format_size(1536) == "1.5 KB"
    assert logic.format_size(5 * 1024 ** 3) == "5.0 GB"
    assert logic.format_size(5000 * 1024 ** 3) == "5000.0 GB"
    assert logic.format_size(None) == ""


# --- the page ---------------------------------------------------------------- #

def test_render_page_escapes_names_and_links():
    name = '<img src=x onerror="alert(1)">.txt'
    href = logic.item_href(TOKEN, 0, name)
    page = logic.render_page("Shared files", [("Shared files", None)],
                             [(name, href, False, 12, href + "?dl")])
    assert "<img" not in page
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;.txt" in page
    assert f'href="{href}?dl"' in page
    assert "12 bytes" in page


def test_render_page_folders_crumbs_and_zip():
    page = logic.render_page(
        "sub - Shared files",
        [("Shared files", f"/{TOKEN}/"), ("docs", f"/{TOKEN}/f/0/docs/"), ("sub", None)],
        [("inner", f"/{TOKEN}/f/0/docs/sub/inner/", True, None,
          f"/{TOKEN}/f/0/docs/sub/inner/?zip")],
        zip_href=f"/{TOKEN}/f/0/docs/sub/?zip", zip_label="Download this folder as ZIP")
    assert f'<a href="/{TOKEN}/">Shared files</a> / ' in page
    assert ">inner/</a>" in page and ">ZIP</a>" in page
    assert "Download this folder as ZIP" in page


def test_render_page_empty_folder():
    page = logic.render_page("x", [("x", None)], [])
    assert "Nothing here." in page
