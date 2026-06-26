# -*- coding: utf-8 -*-
import json
import os

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout
)


def _load_labs():
    this_dir = os.path.dirname(os.path.abspath(__file__))
    labs_path = os.path.join(this_dir, '..', 'core', 'labs.json')
    with open(os.path.abspath(labs_path), 'r', encoding='utf-8') as f:
        return json.load(f)


class CollegeSelectorWidget(QWidget):
    # Emits (college_name, app_name, url) when user clicks Launch
    portal_selected = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = _load_labs()
        self._step1 = None
        self._step2 = None
        self._step2_layout = None
        self._build_ui()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet("CollegeSelectorWidget { background: #f5f0eb; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._step1 = self._build_step1()
        outer.addWidget(self._step1)

        self._step2 = QWidget()
        self._step2_layout = QVBoxLayout(self._step2)
        self._step2_layout.setContentsMargins(0, 0, 0, 0)
        self._step2.hide()
        outer.addWidget(self._step2)

    def _build_step1(self):
        wrapper = QWidget()
        wrapper.setStyleSheet("background: #f5f0eb;")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.addStretch()

        title = QLabel("Select Your College")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 34px; font-weight: 700; color: #292524;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        layout.addWidget(title)

        sub = QLabel("Choose your institution to continue to the exam portal")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            "font-size: 15px; color: #6b7280; margin-top: 6px; margin-bottom: 40px;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        layout.addWidget(sub)

        layout.addSpacing(16)

        # 2×2 grid of college cards
        grid_wrap = QWidget()
        grid_wrap.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_wrap)
        grid.setSpacing(20)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, college in enumerate(self.config.get("colleges", [])):
            btn = self._make_college_btn(college)
            grid.addWidget(btn, idx // 2, idx % 2)

        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(grid_wrap)
        center_row.addStretch()
        layout.addLayout(center_row)

        layout.addStretch()
        return wrapper

    def _make_college_btn(self, college):
        btn = QPushButton(college)
        btn.setFixedSize(240, 110)
        btn.setStyleSheet("""
            QPushButton {
                background: #ffffff;
                color: #292524;
                border: 2px solid #e6dace;
                border-radius: 16px;
                font-size: 26px;
                font-weight: 700;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover {
                background: #292524;
                color: #ffffff;
                border-color: #292524;
            }
            QPushButton:pressed {
                background: #44403c;
                color: #ffffff;
                border-color: #44403c;
            }
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _checked, c=college: self._on_college_clicked(c))
        return btn

    # ── Step 2 ────────────────────────────────────────────────────────────────

    def _on_college_clicked(self, college):
        self._populate_step2(college)
        self._step1.hide()
        self._step2.show()

    def _populate_step2(self, college):
        # Clear old content
        while self._step2_layout.count():
            item = self._step2_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        wrapper = QWidget()
        wrapper.setStyleSheet("background: #f5f0eb;")
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(48, 48, 48, 48)

        # Back button + title row
        top_row = QHBoxLayout()

        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #5c544e;
                border: 1px solid #d6cec5;
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 14px;
                font-weight: 600;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover { background: #ebe4db; color: #292524; }
        """)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._go_back)

        title = QLabel(f"Select Portal")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 30px; font-weight: 700; color: #292524;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )

        college_badge = QLabel(college)
        college_badge.setStyleSheet(
            "background: #292524; color: #ffffff; border-radius: 8px;"
            " padding: 6px 18px; font-size: 15px; font-weight: 700;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        college_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        top_row.addWidget(back_btn)
        top_row.addStretch()
        top_row.addWidget(title)
        top_row.addSpacing(12)
        top_row.addWidget(college_badge)
        top_row.addStretch()
        layout.addLayout(top_row)
        layout.addSpacing(12)

        sub = QLabel("Click a portal card to launch the exam environment")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            "font-size: 14px; color: #9ca3af;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        layout.addWidget(sub)
        layout.addSpacing(36)

        # Portal cards row
        portals = self.config.get("portals", {}).get(college, [])
        cards_row = QHBoxLayout()
        cards_row.setSpacing(28)
        cards_row.addStretch()
        for portal in portals:
            card = self._make_portal_card(college, portal)
            cards_row.addWidget(card)
        cards_row.addStretch()
        layout.addLayout(cards_row)

        layout.addStretch()
        self._step2_layout.addWidget(wrapper)

    def _make_portal_card(self, college, portal):
        app_name = portal.get("app", "")
        slug = portal.get("slug", "")
        url = portal.get("url", "")
        display_url = url.replace("http://", "").replace("https://", "")

        card = QFrame()
        card.setFixedWidth(300)
        card.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 2px solid #e6dace;
                border-radius: 18px;
            }
        """)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(0)

        # College tag badge
        tag_row = QHBoxLayout()
        tag = QLabel(college)
        tag.setStyleSheet(
            "background: #f5f0eb; color: #5c544e; border-radius: 6px;"
            " padding: 3px 10px; font-size: 12px; font-weight: 600;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        tag_row.addWidget(tag)
        tag_row.addStretch()
        layout.addLayout(tag_row)

        layout.addSpacing(16)

        # App / portal name
        name_lbl = QLabel(app_name)
        name_lbl.setStyleSheet(
            "font-size: 24px; font-weight: 700; color: #292524;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        layout.addWidget(name_lbl)

        layout.addSpacing(6)

        # Slug (short name)
        if slug:
            slug_lbl = QLabel(slug)
            slug_lbl.setStyleSheet(
                "font-size: 13px; color: #9ca3af; font-weight: 500;"
                " font-family: 'Segoe UI', system-ui, sans-serif;"
            )
            layout.addWidget(slug_lbl)

        layout.addSpacing(10)

        # URL
        url_lbl = QLabel(display_url)
        url_lbl.setWordWrap(True)
        url_lbl.setStyleSheet(
            "font-size: 13px; color: #6b7280;"
            " font-family: 'Segoe UI', system-ui, sans-serif;"
        )
        layout.addWidget(url_lbl)

        layout.addSpacing(24)

        # Launch button
        launch_btn = QPushButton("Launch →")
        launch_btn.setStyleSheet("""
            QPushButton {
                background: #292524;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 14px 24px;
                font-size: 15px;
                font-weight: 600;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover { background: #44403c; }
            QPushButton:pressed { background: #1c1917; }
        """)
        launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        launch_btn.clicked.connect(
            lambda _checked, c=college, a=app_name, u=url: self.portal_selected.emit(c, a, u)
        )
        layout.addWidget(launch_btn)

        return card

    def _go_back(self):
        self._step2.hide()
        self._step1.show()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_selector(self):
        """Show from step 1 (college selection)."""
        self._step2.hide()
        self._step1.show()
        self.show()
        self.raise_()
