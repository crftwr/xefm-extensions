# LAN Share

An [XeFM](https://github.com/crftwr/xefm) extension: share the selected files
on the local network. XeFM shows a link and a QR code; a phone or any other
device on the same network opens it in a browser and downloads the files.
Nothing is installed on the other device.

- Files download, or play in the browser: videos seek, because the server
  answers range requests.
- Folders can be browsed page by page, or downloaded as a ZIP built while it
  downloads, with no temporary file.
- Anything XeFM can open can be shared: a file on `ssh://` or `s3://`, or one
  inside an archive, goes to the phone straight from where it is, without
  being copied to this machine first.
- Sharing stops when you close the dialog.

## Install

Needs XeFM 1.16.0 or later. The desktop app and the terminal app share
`~/.xefm`, so either way below installs it for both.

**Inside XeFM** (desktop app or terminal): choose **Tools ▸ Advanced ▸ Install
Extension…** and paste

```text
github:crftwr/xefm-extensions/lan-share
```

XeFM downloads and checks the package and lists what it adds: the
`lan-share.share` action and its menu items. Choose **Install** (the dialog
starts on Cancel); XeFM reloads its configuration, and **File ▸ Share on Local
Network…** appears.

**With the `xefm` command** (pip, pipx, uv or the Homebrew formula):

```bash
xefm ext install github:crftwr/xefm-extensions/lan-share
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

## Use

**File ▸ Share on Local Network…**, the row's context menu, or the command
palette (`lan-share.share`).

1. Select the files and folders to share, or put the cursor on one.
2. Choose **Share on Local Network…**. A dialog shows a QR code and the link.
   The link's **Copy** button copies it, to send to a computer.
3. Scan the code with the phone's camera, or open the link in any browser on
   the same network. The page lists what you shared: tap a name to open it,
   **Download** to save it, **ZIP** to get a folder as one file.
4. Close the dialog (`Esc` or `Enter`) to stop sharing. Sharing also stops by
   itself after 30 minutes without a request.

The first time, the operating system may ask whether XeFM (or Python) may
accept incoming connections. Allow it on private networks, or the other device
cannot connect.

In the terminal app the QR code is drawn with text. Over SSH, the link is on
the remote machine's network, and the dialog says so.

## Safety

- The link holds a random token, and the server answers nothing without it.
  Anyone who has the link can download what you shared while the dialog is
  open, so share it only with the devices you mean.
- The connection is plain HTTP: someone on the same network could read the
  files as they go by. Do not share on a public or untrusted network.
- Nothing can be uploaded, changed or deleted. Only what you selected is
  offered: inside a shared folder, names starting with `.` and symbolic links
  are left out, and no path leads outside the folder.

## Settings

Add a `LanShareConfig` class to `~/.xefm/config.py` with only what you want to
change (`xefm ext settings lan-share` prints every default):

```python
class LanShareConfig:
    ADDRESS = ""          # "" the default route's address, "ask" to choose,
                          # "192.168.1.5", or a prefix such as "192.168."
    PORT = 0              # 0 takes any free port; fix one to allow it in a firewall
    IDLE_MINUTES = 30     # stop after this long without a request; 0 never does
    INCLUDE_HIDDEN = False  # offer names starting with "." inside shared folders
    TERMINAL_QR = "light" # the terminal's text: "light" on dark, or "dark" on light
```

`ADDRESS` matters when the machine is on several networks (Wi-Fi and
Ethernet, a VPN, a virtual machine's bridge): the default picks the one this
machine uses to reach the internet, which is usually the one the phone is on.

There is no default key. To bind one, add it to `KEY_BINDINGS` in
`~/.xefm/config.py`:

```python
KEY_BINDINGS = {
    'lan-share.share': ['Ctrl-Shift-S'],
}
```

## Develop

```bash
xefm ext check lan-share
cd lan-share && python -m pytest tests
```

`tests/test_actions.py` needs XeFM importable; the other tests do not.
`tests/test_server.py` starts the server on the loopback address and talks to
it over HTTP.

The package uses only the standard library. The QR code is drawn by
`lan_share/qr.py` (byte mode, level M, versions 1 to 10), so there is nothing
to sync before the first share.

This package uses only XeFM's public API (`xefm.user_api.__all__`).
