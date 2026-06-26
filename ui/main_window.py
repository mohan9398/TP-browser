# -*- coding: utf-8 -*-
from PyQt6.QtCore import QUrl, QTimer, Qt
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QMessageBox, QFrame, QTabWidget, QApplication,
    QDialog, QLabel
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

from secure_browser.core.config import ALLOWED_DOMAINS, APP_VERSION, APP_SECRET_KEY, TARGET_NETLOC
from secure_browser.ui.browser_engine import SecurePage
from secure_browser.ui.college_selector import CollegeSelectorWidget
from secure_browser.network.request_signer import HmacRequestInterceptor
from PyQt6.QtWebEngineCore import QWebEngineProfile


class SecureBrowser(QMainWindow):
    def __init__(self, proxy_origin=None):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window |
            Qt.WindowType.CustomizeWindowHint
        )
        self.setWindowTitle("Secure Exam Browser")
        self.home_view = None
        self._allow_close = False
        self.proxy_origin = proxy_origin
        self._active_college = None

        self.interceptor = HmacRequestInterceptor(APP_SECRET_KEY, parent=self)
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(self.interceptor)

        self.setup_ui()
        self.setup_clipboard_timer()

        # Show college selector on startup — no URL loaded yet
        self.college_selector.show_selector()
        self._set_nav_visible(False)

    # ── UI setup ──────────────────────────────────────────────────────────────

    def setup_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = self.create_toolbar()
        layout.addWidget(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(False)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        layout.addWidget(self.tabs)

        self.setCentralWidget(central)

        self._build_offline_overlay(central)
        self._build_college_selector(central)

        self.setStyleSheet("""
            QMainWindow { background: #f9fafb; }
            QTabWidget::pane { border: none; background: #ffffff; border-top: 1px solid #e5e7eb; }
            QTabBar { background: #f5f0eb; }
            QTabBar::tab { background: transparent; color: #6b7280; padding: 10px 20px; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; font-weight: 500; border-radius: 6px; margin: 4px 2px; }
            QTabBar::tab:selected { background: #ffffff; color: #292524; font-weight: 600; }
            QTabBar::tab:hover:!selected { background: #ebe4db; color: #374151; }
            QTabWidget::tab-bar { alignment: center; }
            QPushButton { background: transparent; color: #5c544e; border: none; padding: 8px 16px; font-family: 'Segoe UI', system-ui, sans-serif; font-weight: 600; font-size: 14px; border-radius: 6px; }
            QPushButton:hover { background: #ebe4db; color: #3c3631; }
            QPushButton:pressed { background: #e0d8ce; }
        """)

    def _build_college_selector(self, parent):
        self.college_selector = CollegeSelectorWidget(parent)
        self.college_selector.portal_selected.connect(self._on_portal_selected)
        self.college_selector.hide()

    def _build_offline_overlay(self, parent):
        self.offline_overlay = QFrame(parent)
        self.offline_overlay.setStyleSheet("QFrame { background: #f5f0eb; }")
        ov = QVBoxLayout(self.offline_overlay)
        ov.setContentsMargins(40, 40, 40, 40)
        ov.addStretch()

        card = QFrame()
        card.setMaximumWidth(540)
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e6dace;"
            " border-radius: 16px; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(48, 44, 48, 44)
        cl.setSpacing(14)

        icon = QLabel("📡")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 52px;")

        title = QLabel("Check your connection")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #292524;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )

        msg = QLabel(
            "We couldn't load the exam page. This is usually a Wi-Fi or "
            "network problem — your exam is fine. Reconnect to a network and "
            "try again."
        )
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            "font-size: 15px; color: #6b7280;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_retry = QPushButton("↻ Try Again")
        btn_retry.setStyleSheet(
            "QPushButton { background: #292524; color: #fff; border: none;"
            " border-radius: 8px; padding: 12px 26px; font-weight: 600;"
            " font-size: 15px; } QPushButton:hover { background: #44403c; }"
        )
        btn_net = QPushButton("📶 Network")
        btn_net.setStyleSheet(
            "QPushButton { background: #ffffff; color: #5c544e;"
            " border: 1px solid #e6dace; border-radius: 8px; padding: 12px 26px;"
            " font-weight: 600; font-size: 15px; }"
            " QPushButton:hover { background: #ebe4db; }"
        )
        btn_retry.clicked.connect(self._retry_load)
        btn_net.clicked.connect(self.open_wifi)
        btn_row.addWidget(btn_net)
        btn_row.addWidget(btn_retry)
        btn_row.addStretch()

        cl.addWidget(icon)
        cl.addWidget(title)
        cl.addWidget(msg)
        cl.addLayout(btn_row)

        card_row = QHBoxLayout()
        card_row.addStretch()
        card_row.addWidget(card)
        card_row.addStretch()
        ov.addLayout(card_row)
        ov.addStretch()

        self.offline_overlay.hide()

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def create_toolbar(self):
        toolbar = QFrame()
        toolbar.setFixedHeight(60)
        toolbar.setStyleSheet("QFrame { background: #f5f0eb; border-bottom: 1px solid #e6dace; }")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 8, 16, 8)

        self.btn_back = QPushButton("← Back")
        self.btn_forward = QPushButton("Forward →")
        self.btn_reload = QPushButton("↻ Reload")
        self.btn_wifi = QPushButton("📶 Network")

        self.btn_back.clicked.connect(self.go_back)
        self.btn_forward.clicked.connect(self.go_forward)
        self.btn_reload.clicked.connect(self.reload_page)
        self.btn_wifi.clicked.connect(self.open_wifi)

        layout.addWidget(self.btn_back)
        layout.addWidget(self.btn_forward)
        layout.addWidget(self.btn_reload)
        layout.addWidget(self.btn_wifi)

        # College name label — shown after a portal is selected
        self.lbl_college = QLabel("")
        self.lbl_college.setStyleSheet(
            "background: #292524; color: #ffffff; border-radius: 8px;"
            " padding: 5px 16px; font-size: 13px; font-weight: 700;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
            " margin-left: 8px;"
        )
        layout.addWidget(self.lbl_college)

        layout.addStretch()

        lbl_version = QLabel(f"v{APP_VERSION}")
        lbl_version.setStyleSheet(
            "color: #a89f91; font-size: 12px; margin-right: 8px; font-weight: 600;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        layout.addWidget(lbl_version)

        # Change Portal button — shown after a portal is selected
        self.btn_change_portal = QPushButton("⊞ Change Portal")
        self.btn_change_portal.setStyleSheet("""
            QPushButton { background: #f5f0eb; color: #5c544e; border: 1px solid #d6cec5; border-radius: 6px; padding: 8px 16px; font-weight: 600; font-size: 13px; margin-right: 8px; font-family: 'Segoe UI', system-ui, sans-serif; }
            QPushButton:hover { background: #ebe4db; color: #292524; border-color: #b5ada5; }
        """)
        self.btn_change_portal.clicked.connect(self._show_college_selector)
        layout.addWidget(self.btn_change_portal)

        btn_exit = QPushButton("Exit Session")
        btn_exit.setStyleSheet("""
            QPushButton { background: #fef2f2; color: #ef4444; font-weight: 600; border-radius: 6px; padding: 8px 20px; border: 1px solid #fca5a5; font-family: 'Segoe UI', system-ui, sans-serif; }
            QPushButton:hover { background: #fee2e2; border-color: #ef4444; color: #dc2626; }
            QPushButton:pressed { background: #fecaca; }
        """)
        btn_exit.clicked.connect(self.confirm_exit)
        layout.addWidget(btn_exit)

        return toolbar

    def _set_nav_visible(self, visible: bool):
        for w in (self.btn_back, self.btn_forward, self.btn_reload,
                  self.btn_wifi, self.lbl_college, self.btn_change_portal):
            w.setVisible(visible)

    # ── College selector integration ──────────────────────────────────────────

    def _show_college_selector(self):
        self.offline_overlay.hide()
        self._set_nav_visible(False)
        self.college_selector.show_selector()
        self._position_college_selector()

    def _on_portal_selected(self, college: str, app_name: str, url: str):
        self._active_college = college
        self.college_selector.hide()

        # Update toolbar
        self.lbl_college.setText(f"{college}  ·  {app_name}")
        self._set_nav_visible(True)

        # Clear any existing tabs, then load the selected URL
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget:
                widget.deleteLater()
        self.home_view = None

        self.create_new_tab(self._build_url(url), f"{college} — {app_name}", is_home=True)

    def _build_url(self, target: str) -> QUrl:
        parsed = QUrl(target)
        # Only route through the local proxy for the face-login server —
        # it rewrites the Origin header so camera permissions work over HTTP.
        # All other URLs (different IPs, Google, etc.) load directly.
        if self.proxy_origin and parsed.host() == TARGET_NETLOC:
            return QUrl(self.proxy_origin + parsed.path())
        return parsed

    # ── Overlay positioning ───────────────────────────────────────────────────

    def _position_college_selector(self):
        if not hasattr(self, 'college_selector'):
            return
        parent = self.college_selector.parentWidget()
        if parent:
            self.college_selector.setGeometry(0, 0, parent.width(), parent.height())

    def _position_overlay(self):
        if not hasattr(self, 'offline_overlay'):
            return
        parent = self.offline_overlay.parentWidget()
        if parent:
            self.offline_overlay.setGeometry(
                0, 60, parent.width(), max(0, parent.height() - 60)
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()
        self._position_college_selector()

    # ── Load state ────────────────────────────────────────────────────────────

    def _retry_load(self):
        self.offline_overlay.hide()
        self.reload_page()

    def _on_load_finished(self, ok):
        if ok:
            self.offline_overlay.hide()
        else:
            self._position_overlay()
            self.offline_overlay.raise_()
            self.offline_overlay.show()

    # ── Clipboard timer ───────────────────────────────────────────────────────

    def setup_clipboard_timer(self):
        self.clipboard = QApplication.clipboard()
        try:
            self.clipboard.clear()
        except Exception:
            pass

        self.clip_timer = QTimer(self)
        self.clip_timer.setSingleShot(True)
        self.clip_timer.timeout.connect(self.clipboard.clear)
        self.clip_timer.start(500)

    # ── Tab management ────────────────────────────────────────────────────────

    def create_new_tab(self, url=QUrl("about:blank"), label="New Tab", is_home=False):
        view = QWebEngineView()
        page = SecurePage(parent=view, browser_window=self)
        view.setPage(page)

        page.featurePermissionRequested.connect(self.handle_permissions)
        page.titleChanged.connect(lambda t, v=view: self.update_tab_title(v, t))
        page.loadFinished.connect(lambda ok, p=page: self.inject_security_js(p))
        page.loadFinished.connect(self._on_load_finished)

        idx = self.tabs.addTab(view, label)
        self.tabs.setCurrentIndex(idx)
        view.setUrl(url)

        if is_home:
            self.home_view = view
        return page

    def update_tab_title(self, view, title):
        idx = self.tabs.indexOf(view)
        if idx != -1:
            short = title[:30] + "..." if len(title) > 30 else title
            self.tabs.setTabText(idx, short)

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        if self.tabs.count() == 1 or widget is self.home_view:
            QMessageBox.information(self, "Info", "Main exam tab cannot be closed")
            return
        self.tabs.removeTab(index)
        if widget:
            widget.deleteLater()

    def current_view(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, QWebEngineView) else None

    # ── Navigation ────────────────────────────────────────────────────────────

    def go_back(self):
        v = self.current_view()
        if v:
            v.back()

    def go_forward(self):
        v = self.current_view()
        if v:
            v.forward()

    def reload_page(self):
        v = self.current_view()
        if v:
            v.reload()

    def open_wifi(self):
        from secure_browser.ui.dialogs import WifiDialog
        dialog = WifiDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload_page()

    # ── Security ──────────────────────────────────────────────────────────────

    def confirm_exit(self):
        reply = QMessageBox.question(
            self, "Confirm Exit", "Exit exam?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._allow_close = True
            self.close()

    def handle_permissions(self, url, feature):
        from PyQt6.QtWebEngineCore import QWebEnginePage as QWEP
        host = url.host().lower()
        if any(d in host for d in ALLOWED_DOMAINS):
            self.sender().setFeaturePermission(url, feature, QWEP.PermissionPolicy.PermissionGrantedByUser)
        else:
            self.sender().setFeaturePermission(url, feature, QWEP.PermissionPolicy.PermissionDeniedByUser)

    def inject_security_js(self, page):
        js = """
        (function() {
            document.addEventListener('contextmenu', e => e.preventDefault());
            document.addEventListener('keydown', function(e) {
                const k = e.key.toLowerCase();
                if (k === 'f12' || k === 'printscreen') {
                    e.preventDefault(); return false;
                }
                if (e.ctrlKey && e.shiftKey && ['i','j','c'].includes(k)) {
                    e.preventDefault(); return false;
                }
            });
        })();
        """
        page.runJavaScript(js)

    def closeEvent(self, event):
        if self._allow_close:
            try:
                self.clip_timer.stop()
            except Exception:
                pass
            event.accept()
        else:
            event.ignore()
