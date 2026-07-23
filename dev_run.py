# -*- coding: utf-8 -*-
"""Developer launcher — runs the browser UI only.

Skips everything in main.py that makes the app hostile to develop against:
no secure desktop, no update check, no process sentinel (which would kill
your own Chrome), no keyboard hook, no Task Manager lockdown. Use this for
UI work; use `python -m secure_browser.main` for a real end-to-end run.

Run from the parent folder of the checkout:

    python -m secure_browser.dev_run
"""
import os
import sys

# Chromium flags must be set before any PyQt6 import — same rule as main.py.
from secure_browser.core.config import QT_FLAGS, ALLOWED_DOMAINS

_origins = ",".join(f"http://{d}" for d in ALLOWED_DOMAINS)
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    f"{QT_FLAGS} "
    f"--unsafely-treat-insecure-origin-as-secure={_origins} "
    f"--user-data-dir={os.path.join(os.environ.get('TEMP', 'C:/Windows/Temp'), 'SecureExamBrowserDevData')}"
)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from secure_browser.ui.main_window import SecureBrowser


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Secure Exam Browser (dev)")

    browser = SecureBrowser(proxy_origin=None)
    # Windowed instead of full-screen, and closable with the X / Alt+F4, so a
    # dev run doesn't trap you behind the exam-mode close guard.
    browser.setWindowFlags(Qt.WindowType.Window)
    browser._allow_close = True
    browser.resize(1280, 820)
    browser.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
