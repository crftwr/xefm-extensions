"""Defaults for the user's settings class (``LanShareConfig`` in config.py)."""


class Settings:
    # Which of this machine's addresses goes into the link:
    #   ""             the one it uses to reach other networks (the default route)
    #   "ask"          choose from a list each time, when there are several
    #   "192.168.1.5"  this address
    #   "192.168."     the first address that starts with this
    ADDRESS = ""

    # The port to listen on; 0 takes any free one. A fixed port is easier to
    # allow in a firewall.
    PORT = 0

    # Stop sharing after this many minutes without a request; 0 never does.
    IDLE_MINUTES = 30

    # Whether names starting with "." inside a shared folder are offered.
    INCLUDE_HIDDEN = False

    # The terminal app draws the QR code with text, which has one colour:
    # "light" suits light text on a dark background, "dark" the opposite.
    TERMINAL_QR = "light"
