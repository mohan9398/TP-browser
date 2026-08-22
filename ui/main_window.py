# -*- coding: utf-8 -*-
from PyQt6.QtCore import QUrl, QTimer, Qt
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QMessageBox, QFrame, QTabWidget, QApplication,
    QDialog, QLabel
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

from secure_browser.core.config import ALLOWED_DOMAINS, APP_VERSION, get_app_secret_key
from secure_browser.ui.browser_engine import SecurePage
from secure_browser.ui.college_selector import CollegeSelectorWidget
from secure_browser.network.netheaders import HmacRequestInterceptor
from secure_browser.network.wifi_manager import WiFiManager
from PyQt6.QtWebEngineCore import QWebEngineProfile


class SecureBrowser(QMainWindow):
    def __init__(self, proxy_routes=None):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window |
            Qt.WindowType.CustomizeWindowHint
        )
        self.setWindowTitle("Secure Exam Browser")
        self.home_view = None
        self._allow_close = False
        # {target_netloc: proxy_origin} — which hosts to route through a proxy.
        # Accept a bare string for backwards compatibility with old callers.
        if isinstance(proxy_routes, str):
            proxy_routes = {}
        self.proxy_routes = proxy_routes or {}
        self._active_college = None

        _key = get_app_secret_key()
        self.interceptor = HmacRequestInterceptor(_key, parent=self)
        del _key  # don't keep the plaintext key sitting in this scope
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(self.interceptor)

        self.setup_ui()
        self.setup_clipboard_timer()
        self._update_wifi_label()

        # Show college selector on startup — no URL loaded yet
        self.college_selector.show_selector()
        self._set_nav_visible(False)
        self._position_version_badge()

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
        self._build_version_badge(central)

        self.setStyleSheet("""
            QMainWindow { background: #0f1e21; }
            QTabWidget::pane { border: none; background: #ffffff; border-top: 1px solid #24393e; }
            QTabBar { background: #0a1618; }
            QTabBar::tab { background: transparent; color: #8ba1a5; padding: 9px 20px; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 13px; font-weight: 600; border-radius: 6px; margin: 4px 2px; }
            QTabBar::tab:selected { background: #123c42; color: #4fc3cf; }
            QTabBar::tab:hover:!selected { background: #16292d; color: #eef4f5; }
            QTabWidget::tab-bar { alignment: center; }
            QPushButton { background: transparent; color: #b6c8cb; border: none; padding: 8px 14px; font-family: 'Segoe UI', system-ui, sans-serif; font-weight: 600; font-size: 13px; border-radius: 6px; }
            QPushButton:hover { background: #1b3237; color: #eef4f5; }
            QPushButton:pressed { background: #24393e; }
        """)

    def _build_version_badge(self, parent):
        self.lbl_version = QLabel(f"v{APP_VERSION}", parent)
        self.lbl_version.setStyleSheet(
            "background: rgba(255, 255, 255, 0.07); color: #8ba1a5;"
            " border-radius: 9px; padding: 3px 10px; font-size: 11px;"
            " font-weight: 600; font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        self.lbl_version.adjustSize()
        self.lbl_version.show()

    def _build_college_selector(self, parent):
        self.college_selector = CollegeSelectorWidget(parent)
        self.college_selector.portal_selected.connect(self._on_portal_selected)
        self.college_selector.exit_requested.connect(self.confirm_exit)
        self.college_selector.hide()

    def _build_offline_overlay(self, parent):
        self.offline_overlay = QFrame(parent)
        self.offline_overlay.setStyleSheet("QFrame { background: #0f1e21; }")
        ov = QVBoxLayout(self.offline_overlay)
        ov.setContentsMargins(40, 40, 40, 40)
        ov.addStretch()

        card = QFrame()
        card.setMaximumWidth(540)
        card.setStyleSheet(
            "QFrame { background: #16292d; border: 1px solid #24393e;"
            " border-radius: 12px; }"
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
            "font-size: 22px; font-weight: 700; color: #eef4f5;"
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
            "font-size: 15px; color: #8ba1a5;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_retry = QPushButton("↻ Try Again")
        btn_retry.setStyleSheet(
            "QPushButton { background: #17808a; color: #fff; border: none;"
            " border-radius: 8px; padding: 12px 26px; font-weight: 600;"
            " font-size: 15px; } QPushButton:hover { background: #1c99a5; }"
        )
        btn_net = QPushButton("📶 Network")
        btn_net.setStyleSheet(
            "QPushButton { background: #16292d; color: #b6c8cb;"
            " border: 1px solid #33525a; border-radius: 8px; padding: 12px 26px;"
            " font-weight: 600; font-size: 15px; }"
            " QPushButton:hover { background: #1b3237; border-color: #17808a; }"
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
        toolbar.setStyleSheet("QFrame { background: #0a1618; border-bottom: 1px solid #24393e; }")
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
            "background: #123c42; color: #4fc3cf; border: 1px solid #33525a;"
            " border-radius: 6px; padding: 5px 14px; font-size: 12px; font-weight: 700;"
            " letter-spacing: 0.3px;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
            " margin-left: 8px;"
        )
        layout.addWidget(self.lbl_college)

        layout.addStretch()

        # Change Portal button — shown after a portal is selected
        self.btn_change_portal = QPushButton("⊞ Change Portal")
        self.btn_change_portal.setStyleSheet("""
            QPushButton { background: #16292d; color: #b6c8cb; border: 1px solid #33525a; border-radius: 6px; padding: 8px 16px; font-weight: 600; font-size: 13px; margin-right: 8px; font-family: 'Segoe UI', system-ui, sans-serif; }
            QPushButton:hover { background: #1b3237; color: #eef4f5; border-color: #17808a; }
        """)
        self.btn_change_portal.clicked.connect(self._show_college_selector)
        layout.addWidget(self.btn_change_portal)

        btn_exit = QPushButton("Exit Session")
        btn_exit.setStyleSheet("""
            QPushButton { background: #3b1616; color: #f08a7a; font-weight: 600; border-radius: 6px; padding: 8px 20px; border: 1px solid #7a2f2f; font-family: 'Segoe UI', system-ui, sans-serif; }
            QPushButton:hover { background: #5b1d1d; border-color: #b0472f; color: #ffffff; }
            QPushButton:pressed { background: #7a2626; }
        """)
        btn_exit.clicked.connect(self.confirm_exit)
        layout.addWidget(btn_exit)

        # Prevent toolbar buttons from grabbing keyboard focus. Otherwise a
        # focused QPushButton fires its clicked signal on Space/Enter — so a
        # student pressing Space would accidentally trigger "Exit Session"
        # (or another button) instead of scrolling the exam page.
        for w in (self.btn_back, self.btn_forward, self.btn_reload,
                  self.btn_wifi, self.btn_change_portal, btn_exit):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        return toolbar

    def _set_nav_visible(self, visible: bool):
        for w in (self.btn_back, self.btn_forward, self.btn_reload,
                  self.btn_wifi, self.lbl_college, self.btn_change_portal):
            w.setVisible(visible)

    # ── College selector integration ──────────────────────────────────────────

    def _clear_all_tabs(self):
        """Stop and destroy every tab. Destroying the QWebEngineView tears
        down the page's JS context, which releases any active getUserMedia
        stream -- otherwise the camera stays on behind whatever is shown next."""
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget:
                try:
                    widget.stop()
                    widget.page().loadFinished.disconnect(self._on_load_finished)
                except (RuntimeError, TypeError):
                    pass
                widget.deleteLater()
        self.home_view = None

    def _show_college_selector(self):
        self.offline_overlay.hide()
        # Destroy the live exam page before showing the selector -- otherwise
        # its camera stream keeps running behind the overlay.
        self._clear_all_tabs()
        self._set_nav_visible(False)
        self.college_selector.show_selector()
        self._position_college_selector()
        self._position_version_badge()

    def _on_portal_selected(self, college: str, app_name: str, url: str):
        self._active_college = college
        self.college_selector.hide()

        # Update toolbar
        self.lbl_college.setText(f"{college}  ·  {app_name}")
        self._set_nav_visible(True)

        # Clear any existing tabs, then load the selected URL.
        # Stop in-flight loads first — otherwise a stale loadFinished(False)
        # from the old page can fire after the new tab is already up and
        # trigger the "no internet" overlay over a perfectly working page.
        self._clear_all_tabs()

        self.create_new_tab(self._build_url(url), f"{college} — {app_name}", is_home=True)

    def _build_url(self, target: str) -> QUrl:
        parsed = QUrl(target)
        # Route through the local proxy only for configured target servers —
        # the proxy rewrites the Origin header so camera permissions work over
        # HTTP. All other URLs (Test Center, Google, etc.) load directly.
        #
        # Match on EXACT host[:port] so two targets on the same host but
        # different ports stay distinct (e.g. 192.168.2.5:81 vs 192.168.2.5).
        # A URL with a port that isn't a configured target must NOT fall back to
        # a same-host proxy on a different port — that would mis-route it.
        # Requires the URL to have a real scheme (http://) — without it QUrl
        # can't parse the host and nothing gets proxied.
        host = parsed.host()
        netloc = f"{host}:{parsed.port()}" if parsed.port() != -1 else host
        proxy_origin = self.proxy_routes.get(netloc)
        if proxy_origin:
            tail = parsed.path()
            if parsed.query():
                tail += "?" + parsed.query()
            return QUrl(proxy_origin + tail)
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

    def _position_version_badge(self):
        if not hasattr(self, 'lbl_version'):
            return
        parent = self.lbl_version.parentWidget()
        if parent:
            margin = 12
            self.lbl_version.move(margin, parent.height() - self.lbl_version.height() - margin)
            self.lbl_version.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()
        self._position_college_selector()
        self._position_version_badge()

    # ── Load state ────────────────────────────────────────────────────────────

    def _retry_load(self):
        self.offline_overlay.hide()
        self.reload_page()

    def _on_load_finished(self, ok):
        # Ignore signals from a page that is no longer the active tab — this
        # can happen when a stale/queued signal from a just-replaced tab
        # arrives after the new tab has already loaded successfully.
        current = self.current_view()
        sender_page = self.sender()
        if current is None or sender_page is not current.page():
            return

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
            try:
                widget.stop()
                widget.page().loadFinished.disconnect(self._on_load_finished)
            except (RuntimeError, TypeError):
                pass
            widget.deleteLater()

    def current_view(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, QWebEngineView) else None

    # ── Navigation ────────────────────────────────────────────────────────────

    def go_back(self):
        v = self.current_view()
        if not v:
            return
        # Within the exam site, Back walks the page's own history. Once that
        # history is exhausted (we're at the portal's first page), Back leaves
        # the site entirely and returns to the portal-selection screen -- which
        # is an overlay, not a history entry, so v.back() can't reach it.
        if v.history().canGoBack():
            v.back()
        else:
            self._show_college_selector()

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
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._update_wifi_label()
        if accepted:
            self.reload_page()

    def _update_wifi_label(self):
        """Show the connected Wi-Fi SSID on the toolbar button instead of the
        generic 'Network' label, so the user can see at a glance which
        network they're on. Clicking it still opens the same Wi-Fi manager.
        """
        ssid = WiFiManager.get_current_ssid()
        self.btn_wifi.setText(f"📶 {ssid}" if ssid else "📶 Network")

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
