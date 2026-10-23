# Size & Date Filters

An [XeFM](https://github.com/crftwr/xefm) extension: pane filters that ask about
the *file* rather than its name — large files, and files modified recently.

| Filter | Shows files that are… |
|---|---|
| **Over 100 MB** | larger than 100 MB |
| **Over 1 GB** | larger than 1 GB |
| **Modified today** | modified since local midnight |
| **Modified in the last 7 days** | modified within the last 7 × 24 hours |

Directories always stay visible, as with any XeFM filter, so you can still open
them.

## Install

Needs XeFM 1.10.0 or later. The desktop app and the terminal app share
`~/.xefm`, so either way below installs it for both.

**Inside XeFM** (desktop app or terminal): choose **Tools ▸ Advanced ▸ Install
Extension…** and paste

```text
github:crftwr/xefm-extensions/size-date-filters
```

XeFM downloads and checks the package and lists what it adds: four filters.
Choose **Install** (the dialog starts on Cancel); XeFM reloads its
configuration.

**With the `xefm` command** (pip, pipx, uv or the Homebrew formula):

```bash
xefm ext install github:crftwr/xefm-extensions/size-date-filters
```

Then run **Tools ▸ Reload Configuration** in XeFM, or restart it.

**On XeFM 1.9.0**, install version 0.1.0 instead: add
`@size-date-filters-v0.1.0` to the source for the `xefm` command. 1.9.0's
Install Extension takes only the package under the cursor, so in the app
download
[size-date-filters-v0.1.0.zip](https://github.com/crftwr/xefm-extensions/archive/refs/tags/size-date-filters-v0.1.0.zip),
extract it (**File ▸ Extract Archive…**), open the extracted folder, put the
cursor on `size-date-filters` and choose **Tools ▸ Advanced ▸ Install
Extension…**.

## Use

Open the Filter dialog (`;` in the AFX keymap, or **View ▸ Filter…**). The four
filters are fixed rows under **(clear filter)**. Pick one and press `Enter`. To
go back to everything, pick **(clear filter)**.

The filters read only the size and date XeFM already collected for the
listing, so they cost nothing extra on network drives, SSH or S3.

The thresholds are fixed. For other values, write your own in `FILTERS` in
`~/.xefm/config.py`, in the same shape as this package's
[`filters.py`](size_date_filters/filters.py).

## Develop

```bash
xefm ext check size-date-filters
cd size-date-filters && python -m pytest tests
```

The tests do not need XeFM. The package has no actions and imports nothing
from XeFM. `FILTERS` is still Preview (`API_VERSION` 0) and may change.
