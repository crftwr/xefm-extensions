"""Show files in the Quick Look panel — the panel Finder opens with Space.

Run as a script: ``python quicklook_helper.py <file> [<file> ...]``.

Why a process of its own, and not ``qlmanage -p``:

- ``qlmanage`` is a debug tool. Its panel can open behind the window that
  asked for it, and when it closes macOS picks which app comes forward.
- This helper brings the panel to the front itself, remembers which app was
  in front before (XeFM's window, or the terminal XeFM runs in), and hands
  the keyboard back to exactly that app when the panel closes.
- With several files, the arrow keys step through them as in Finder.
- One mechanism serves the desktop app and the terminal app alike, and no
  window-system code enters XeFM's own process.

It runs as an accessory app: no Dock icon, no menu bar. It ends when the
panel closes, and also when the user switches to another app, so a panel
never stays behind without an owner.

Where PyObjC cannot be imported, it becomes ``qlmanage -p`` instead.
"""

import os
import sys

QLMANAGE = "/usr/bin/qlmanage"

#: NSApplicationActivateIgnoringOtherApps. macOS 14 deprecated it and ignores
#: it; earlier systems need it to bring another app forward.
_ACTIVATE_IGNORING_OTHER_APPS = 1 << 1


def existing(paths):
    """The paths that are there, absolute, in the order given."""
    return [os.path.abspath(p) for p in paths if os.path.exists(p)]


def quiet_system_log():
    """Send what the system writes to standard error to /dev/null, and keep
    Python's own ``sys.stderr`` (this helper's messages, a traceback) on the
    real one.

    XeFM shows a program's standard error in its log, and AppKit writes
    diagnostics there that mean nothing to the user. With a Japanese input
    source, every run printed ``error messaging the mach port for
    IMKCFRunLoopWakeUpReliable`` (InputMethodKit, about a process that is
    not an app bundle). Those go to file descriptor 2 directly, so that is
    what is redirected."""
    sys.stderr.flush()
    kept = os.dup(2)
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 2)
    os.close(null)
    sys.stderr = os.fdopen(kept, "w", buffering=1, encoding="utf-8",
                           errors="replace")


def run_qlmanage(paths):
    """Replace this process with ``qlmanage -p``, its diagnostics discarded."""
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    os.execv(QLMANAGE, [QLMANAGE, "-p", *paths])


def run_panel(paths):
    import objc
    from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory,
                        NSApplicationActivationPolicyRegular, NSObject,
                        NSWorkspace)
    from Foundation import NSURL, NSTimer
    from Quartz import QLPreviewPanel

    class PreviewController(
            NSObject,
            protocols=[objc.protocolNamed("NSApplicationDelegate"),
                       objc.protocolNamed("QLPreviewPanelDataSource"),
                       objc.protocolNamed("QLPreviewPanelDelegate")]):

        def initWithURLs_previous_(self, urls, previous):
            self = objc.super(PreviewController, self).init()
            if self is None:
                return None
            self.urls = urls
            self.previous = previous
            self.finished = False
            self.shown = False
            return self

        # -- the application ------------------------------------------------

        def applicationDidFinishLaunching_(self, notification):
            app = NSApplication.sharedApplication()
            panel = QLPreviewPanel.sharedPreviewPanel()
            workspace = NSWorkspace.sharedWorkspace()
            workspace.notificationCenter().addObserver_selector_name_object_(
                self, b"otherAppActivated:",
                "NSWorkspaceDidActivateApplicationNotification", None)
            app.activateIgnoringOtherApps_(True)
            # The panel looks along the responder chain for its controller
            # and finds this delegate (acceptsPreviewPanelControl: below).
            panel.makeKeyAndOrderFront_(None)
            if panel.dataSource() is None:
                # No window of ours is in the chain on this system: take the
                # panel directly.
                panel.setDataSource_(self)
                panel.setDelegate_(self)
                panel.reloadData()
            # Esc, Space and the close button only order the panel out; no
            # window-close notification comes. So watch whether it is still
            # on screen.
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.1, self, b"watchPanel:", None, True)

        def otherAppActivated_(self, notification):
            # The user went to another app. The panel has no Dock icon to
            # come back through, so it does not outlive that. A system
            # prompt is not such an app: Quick Look's audio preview asks
            # for the microphone the first time, and the panel must survive
            # that question.
            other = notification.userInfo().get("NSWorkspaceApplicationKey")
            if (other is None or other.processIdentifier() == os.getpid()
                    or other.activationPolicy()
                    != NSApplicationActivationPolicyRegular):
                return
            self.finish()

        # -- QLPreviewPanelController ---------------------------------------

        @objc.typedSelector(b"Z@:@")
        def acceptsPreviewPanelControl_(self, panel):
            return True

        def beginPreviewPanelControl_(self, panel):
            panel.setDataSource_(self)
            panel.setDelegate_(self)

        def endPreviewPanelControl_(self, panel):
            pass

        # -- QLPreviewPanelDataSource ---------------------------------------

        def numberOfPreviewItemsInPreviewPanel_(self, panel):
            return len(self.urls)

        def previewPanel_previewItemAtIndex_(self, panel, index):
            return self.urls[index]

        # -- closing --------------------------------------------------------

        def watchPanel_(self, timer):
            visible = QLPreviewPanel.sharedPreviewPanel().isVisible()
            if visible:
                self.shown = True
            elif self.shown:
                timer.invalidate()
                self.finish()

        def finish(self):
            if self.finished:
                return
            self.finished = True
            app = NSApplication.sharedApplication()
            previous = self.previous
            # Hand the keyboard back to the app that asked, but only when the
            # panel still had it: if the user chose another app, that stands.
            if (previous is not None and app.isActive()
                    and not previous.isTerminated()):
                if hasattr(app, "yieldActivationToApplication_"):
                    app.yieldActivationToApplication_(previous)    # macOS 14+
                previous.activateWithOptions_(_ACTIVATE_IGNORING_OTHER_APPS)
            app.terminate_(None)

    previous = NSWorkspace.sharedWorkspace().frontmostApplication()
    urls = [NSURL.fileURLWithPath_(p) for p in paths]
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = PreviewController.alloc().initWithURLs_previous_(urls, previous)
    app.setDelegate_(controller)
    app.run()


def main(argv):
    paths = existing(argv)
    if not paths:
        sys.stderr.write("Quick Look: none of the files exist\n")
        return 2
    try:
        import AppKit    # noqa: F401
        import Quartz    # noqa: F401
    except ImportError:
        run_qlmanage(paths)
    quiet_system_log()
    run_panel(paths)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
