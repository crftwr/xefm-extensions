class Settings:
    # The Git tool Open Git Tool starts in the repository: a command line or
    # an argv list. Changing the repository is its job, not XeFM's.
    TOOL = "lazygit"
    # True for a program that runs in a terminal (lazygit, tig, gitui), False
    # for a desktop client (["open", "-a", "Fork", "."], "github .").
    TOOL_TERMINAL = True
    # How many commits File History lists.
    LOG_LIMIT = 200
