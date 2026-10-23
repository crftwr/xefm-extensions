import io

import pytest

from line_count import logic
from line_count.logic import Binary, Counts, count_stream, result_markdown, walk


def count(data, **kw):
    return count_stream(io.BytesIO(data), **kw)


def test_counts_like_an_editor():
    assert count(b"a b\ncc\n") == Counts(lines=2, words=3, chars=7)
    assert count(b"a b\ncc") == Counts(lines=2, words=3, chars=6)   # no final \n
    assert count(b"") == Counts(0, 0, 0)
    assert count(b"\n\n") == Counts(lines=2, words=0, chars=2)


def test_utf8_characters_and_unicode_spaces():
    text = "日本語　テキスト\n"          # an ideographic space between words
    assert count(text.encode()) == Counts(lines=1, words=2, chars=len(text))


def test_invalid_utf8_counts_one_char_per_bad_byte():
    assert count(b"a\xffb").chars == 3


def test_bom_is_not_a_character():
    assert count(b"\xef\xbb\xbfab").chars == 2


def test_binary_is_refused():
    with pytest.raises(Binary):
        count(b"PK\x03\x04\0\0rest")


def test_words_and_chars_across_chunk_boundaries(monkeypatch):
    monkeypatch.setattr(logic, "CHUNK", 3)
    data = "hello wörld\nfoo  bar\n".encode()   # ö splits across a chunk
    assert count(data) == Counts(lines=2, words=4, chars=len(data.decode()))


def test_cancel_stops_reading():
    calls = []
    count(b"x" * 10, cancelled=lambda: calls.append(1) or True)
    assert len(calls) == 1


def test_on_read_reports_bytes(monkeypatch):
    monkeypatch.setattr(logic, "CHUNK", 4)
    seen = []
    count(b"0123456789", on_read=seen.append)
    assert seen == [4, 8, 10]


class FakePath:
    def __init__(self, name, children=None):
        self.name, self.children = name, children

    def is_dir(self):
        return self.children is not None

    def iterdir(self):
        return iter(self.children)


def test_walk_a_file_is_itself():
    f = FakePath("a.py")
    assert list(walk(f, "a.py")) == [("a.py", f)]


def test_walk_skips_hidden_and_keeps_order():
    tree = FakePath("src", [
        FakePath("b.py"), FakePath(".git", [FakePath("HEAD")]),
        FakePath("pkg", [FakePath("z.py"), FakePath(".cache")]),
        FakePath("A.py"),
    ])
    assert [n for n, _ in walk(tree, "src")] == [
        "src/A.py", "src/b.py", "src/pkg/z.py"]


def test_walk_survives_an_unreadable_folder():
    class Broken(FakePath):
        def iterdir(self):
            raise PermissionError("denied")
    tree = FakePath("d", [Broken("locked", []), FakePath("ok.txt")])
    assert [n for n, _ in walk(tree, "d")] == ["d/ok.txt"]


def md(results, binary=(), failed=(), **kw):
    return result_markdown(list(results), list(binary), list(failed),
                           md_escape=lambda s: s.replace("|", "\\|"),
                           md_code_block=lambda s: f"```\n{s}\n```", **kw)


def test_markdown_sorted_with_total():
    out = md([("a.py", Counts(10, 20, 100)), ("b.py", Counts(30, 5, 50))])
    assert out.index("b.py") < out.index("a.py")
    assert "40 lines  25 words  150 characters  (2 files)" in out
    assert "**Total**" in out


def test_markdown_single_file_has_no_total_row():
    out = md([("a.py", Counts(1, 1, 2))])
    assert "**Total**" not in out
    assert "(1 file)" in out


def test_markdown_caps_rows_but_not_totals():
    rows = [(f"f{i}", Counts(i, 0, 0)) for i in range(5)]
    out = md(rows, max_rows=2)
    assert "f4" in out and "f3" in out and "f2" not in out
    assert "10 lines" in out and "all 5" in out


def test_markdown_lists_binary_and_failures_and_escapes():
    out = md([], binary=["x.png"], failed=[("a|b.txt", "denied")])
    assert "No text files" in out
    assert "x.png" in out and "a\\|b.txt: denied" in out
