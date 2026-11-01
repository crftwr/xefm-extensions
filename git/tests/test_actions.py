"""The actions against a fake ctx shaped like xefm.user_api's, over a real
scratch repository. Needs XeFM importable."""

import os
from types import SimpleNamespace

import pytest

pytest.importorskip("xefm.user_api")

from xefm_git import actions, repo  # noqa: E402
from xefm_git.settings import Settings  # noqa: E402


class Path:
    """What the actions read of XeFM's Path: str(), name, parent, scheme."""

    def __init__(self, text):
        self.text = str(text)

    def __str__(self):
        return self.text

    @property
    def scheme(self):
        return "git" if self.text.startswith("git://") else "file"

    @property
    def name(self):
        return self.text.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]

    @property
    def parent(self):
        return Path(os.path.dirname(self.text))


def entry(path, is_dir=False):
    path = Path(path)
    return SimpleNamespace(path=path, name=path.name, is_dir=is_dir)


class FakeCtx:
    def __init__(self, folder, focused=None):
        self.pane = SimpleNamespace(path=Path(folder), focused=focused,
                                    cd=self._cd, open_list=self._open_list,
                                    refresh=lambda: self.refreshed.append(True))
        self.messages, self.diffs, self.choices, self.lists = [], [], [], []
        self.cds, self.programs, self.refreshed = [], [], []
        self.pending = []

    def _cd(self, target, focus_name=None):
        self.cds.append((str(target), focus_name))

    def _open_list(self, paths, *, title):
        self.lists.append((list(paths), title))

    def message(self, text):
        self.messages.append(text)

    def diff(self, left, right, *, left_title=None, right_title=None):
        self.diffs.append((str(getattr(left, "path", left)),
                           str(getattr(right, "path", right)), left_title, right_title))

    def choose(self, title, items, *, type="choice", on_result=None):
        self.choices.append((title, list(items), type))
        self.pending.append(on_result)

    def answer(self, pick):
        """The user's answer to the last prompt — after the action returned."""
        callback = self.pending.pop()
        items = self.choices[-1][1]
        callback(pick(items) if callable(pick) else pick)

    def run_task(self, title, work, *, on_done=None, read_only=False):
        assert read_only
        value = work(SimpleNamespace(checkpoint=lambda: None, cancelled=lambda: False))
        on_done(self, SimpleNamespace(ok=True, status="done", value=value))

    def run_program(self, command, *, terminal=False, cwd=None):
        self.programs.append((command, terminal, cwd))


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    values = type("S", (Settings,), {})
    handle = SimpleNamespace(settings=values)
    monkeypatch.setattr(actions, "extension",
                        lambda module: handle if module.startswith("xefm_git.") else None)
    return values


def test_outside_a_work_tree_says_so(tmp_path):
    for action in (actions.changed, actions.browse, actions.open_tool):
        ctx = FakeCtx(tmp_path)
        action(ctx)
        assert ctx.messages and "Git working tree" in ctx.messages[0]


def test_changed_opens_every_change_as_one_list(work):
    ctx = FakeCtx(os.path.join(work, "src"))
    actions.changed(ctx)
    (paths, title), = ctx.lists
    assert title == "Git changes — proj"
    assert sorted(os.path.relpath(p, work) for p in paths) == sorted(
        ["docs", "notes.txt", "README.md", os.path.join("src", "app.py"),
         os.path.join("src", "new.py")])


def test_changed_in_a_clean_tree(work):
    repo.run(work, "stash", "-u", "-q")
    ctx = FakeCtx(work)
    actions.changed(ctx)
    assert ctx.lists == [] and ctx.messages == [f"Git: no changes in {work}"]


def test_diff_head_compares_head_with_the_working_file(work):
    app = os.path.join(work, "src", "app.py")
    ctx = FakeCtx(os.path.join(work, "src"), entry(app))
    actions.diff_head(ctx)
    assert ctx.diffs == [(repo.uri(work, "HEAD", "src/app.py"), app,
                          "HEAD: src/app.py", "Working tree")]


def test_diff_head_in_a_flat_list_rooted_higher_up(work):
    """Changed Files lists src/app.py in a pane whose path is the top."""
    app = os.path.join(work, "src", "app.py")
    ctx = FakeCtx(work, entry(app))
    actions.diff_head(ctx)
    assert ctx.diffs[0][0] == repo.uri(work, "HEAD", "src/app.py")


def test_log_in_a_flat_list_rooted_higher_up(work):
    ctx = FakeCtx(work, entry(os.path.join(work, "src", "app.py")))
    actions.log(ctx)
    assert ctx.choices[0][0] == "History of app.py"
    assert len(ctx.choices[0][1]) == 2


def test_diff_head_on_a_new_file(work):
    ctx = FakeCtx(work, entry(os.path.join(work, "notes.txt")))
    actions.diff_head(ctx)
    assert ctx.diffs == [] and "not in HEAD" in ctx.messages[0]


def test_diff_head_on_a_folder(work):
    ctx = FakeCtx(work, entry(os.path.join(work, "src"), is_dir=True))
    actions.diff_head(ctx)
    assert ctx.diffs == [] and "works on a file" in ctx.messages[0]


def test_diff_head_in_a_revision_folder_compares_with_the_working_tree(work):
    uri = repo.uri(work, "v1", "src/app.py")
    ctx = FakeCtx(repo.uri(work, "v1", "src"), entry(uri))
    actions.diff_head(ctx)
    assert ctx.diffs == [(uri, os.path.join(work, "src", "app.py"),
                          "v1: src/app.py", "Working tree")]


def test_browse_opens_the_chosen_revision_at_the_same_folder(work):
    ctx = FakeCtx(os.path.join(work, "src"), entry(os.path.join(work, "src", "app.py")))
    actions.browse(ctx)
    title, items, kind = ctx.choices[0]
    assert kind == "filter" and items[0] == "HEAD"
    ctx.answer(lambda items: items.index("v1  (tag)"))
    assert ctx.cds == [(repo.uri(work, "v1", "src"), "app.py")]


def test_browse_falls_back_to_the_top_where_the_folder_is_missing(work):
    ctx = FakeCtx(os.path.join(work, "docs"))
    actions.browse(ctx)
    ctx.answer(0)
    assert ctx.cds == [(repo.uri(work, "HEAD"), None)]


def test_browse_cancelled(work):
    ctx = FakeCtx(work)
    actions.browse(ctx)
    ctx.answer(None)
    assert ctx.cds == []


def history_of(work, rel):
    ctx = FakeCtx(os.path.dirname(os.path.join(work, rel)), entry(os.path.join(work, rel)))
    actions.log(ctx)
    return ctx


def test_log_lists_the_commits(work):
    ctx = history_of(work, "src/app.py")
    title, items, kind = ctx.choices[0]
    assert title == "History of app.py" and kind == "filter"
    assert [i.split("  ")[-1] for i in items] == ["Second", "First"]


def test_log_then_compare_with_the_working_file(work):
    ctx = history_of(work, "src/app.py")
    ctx.answer(1)                                   # "First"
    ctx.answer(actions.COMPARE_WORKING)
    (left, right, lt, rt), = ctx.diffs
    first = repo.commit_of(work, "HEAD~1")
    assert left == repo.uri(work, first, "src/app.py")
    assert right == os.path.join(work, "src", "app.py")
    assert lt == f"{first[:7]}: src/app.py" and rt == "Working tree"


def test_log_then_compare_with_the_version_before(work):
    ctx = history_of(work, "src/app.py")
    ctx.answer(0)                                   # "Second"
    ctx.answer(actions.COMPARE_PARENT)
    second = repo.commit_of(work, "HEAD")
    assert ctx.diffs[0][:2] == (repo.uri(work, f"{second}^", "src/app.py"),
                                repo.uri(work, second, "src/app.py"))


def test_log_the_version_before_the_first(work):
    ctx = history_of(work, "src/app.py")
    ctx.answer(1)
    ctx.answer(actions.COMPARE_PARENT)
    assert ctx.diffs == [] and "no version before" in ctx.messages[0]


def test_log_then_open_the_revision_s_folder(work):
    ctx = history_of(work, "src/app.py")
    ctx.answer(1)
    ctx.answer(actions.OPEN_FOLDER)
    first = repo.commit_of(work, "HEAD~1")
    assert ctx.cds == [(repo.uri(work, first, "src"), "app.py")]


def test_log_limit_comes_from_the_settings(work, settings):
    settings.LOG_LIMIT = 1
    ctx = history_of(work, "src/app.py")
    assert len(ctx.choices[0][1]) == 1


def test_open_tool_runs_the_configured_command_at_the_top(work, settings):
    settings.TOOL, settings.TOOL_TERMINAL = ["git", "status"], False
    ctx = FakeCtx(os.path.join(work, "src"))
    actions.open_tool(ctx)
    assert ctx.programs == [(["git", "status"], False, work)]
    assert ctx.refreshed


def test_open_tool_without_the_program(work, settings):
    settings.TOOL = "no-such-git-tool --flag"
    ctx = FakeCtx(work)
    actions.open_tool(ctx)
    assert ctx.programs == [] and "no-such-git-tool is not on PATH" in ctx.messages[0]
