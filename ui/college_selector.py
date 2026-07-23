# -*- coding: utf-8 -*-
import json
import os

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout,
    QScrollArea, QGraphicsDropShadowEffect, QSizePolicy
)

FONT = "'Segoe UI', 'Inter', system-ui, sans-serif"

# Palette — deep charcoal-teal, keyed off the logos' teal rather than navy.
BG_PAGE = "#0f1e21"
BG_HEADER = "#0a1618"
BG_CARD = "#16292d"
BG_CARD_HOVER = "#1b3237"
BG_CARD_SELECTED = "#1c3439"
BORDER = "#24393e"
BORDER_STRONG = "#33525a"
TEXT = "#eef4f5"
TEXT_DIM = "#b6c8cb"
TEXT_MUTED = "#8ba1a5"
GOLD = "#e3b23c"            # section labels, selected state
GOLD_DEEP = "#8a6a1f"
ACCENT = "#17808a"          # logo teal — primary actions
ACCENT_HOVER = "#1c99a5"
ACCENT_SOFT = "#123c42"
ORANGE = "#e2611a"          # logo orange — reserved, used sparingly

LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _asset_dirs():
    """Directories that may hold bundled assets, in lookup order.

    Same rule as labs.json: next to the exe first (Nuitka standalone does not
    set sys.frozen), then the source tree for dev runs.
    """
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.dirname(os.path.abspath(sys.executable)),
        os.path.abspath(os.path.join(here, '..')),
    ]


def _find_logo(college):
    """Locate images/<college>-bg.<ext> for a college, case-insensitively.

    Returns None when no logo ships for that college — the tile then falls
    back to a text monogram rather than breaking the screen.
    """
    stem = college.lower()
    for base in _asset_dirs():
        for ext in LOGO_EXTENSIONS:
            path = os.path.join(base, 'images', f'{stem}-bg{ext}')
            if os.path.exists(path):
                return path
    return None


def _logo_pixmap(path, width, height, ink=TEXT):
    """Load a logo, scale it, drop its white background, and lighten the ink.

    The shipped crests are opaque white JPEGs with black wordmarks. Two things
    have to happen before they can sit on a dark card:

    1. White becomes transparent — otherwise every logo paints a white block.
       This is the exact inverse of compositing the artwork over white: alpha
       comes from how far the darkest channel falls from 255, and the colour is
       un-composited so the teal and orange stay true instead of washing out.
    2. The near-grey pixels (the black wordmark and its antialiased edges) are
       repainted in `ink`, since black text on a dark card is unreadable. The
       coloured swoosh has a wide channel spread and is left untouched, so the
       brand colours survive.

    Scaling happens first so the per-pixel pass only touches display-sized
    images (a few thousand pixels) rather than the full-resolution source.
    """
    ink_colour = QColor(ink)
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None

    pixmap = pixmap.scaled(
        width, height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            r, g, b = colour.red(), colour.green(), colour.blue()
            alpha = 255 - min(r, g, b)
            if alpha <= 0:
                image.setPixelColor(x, y, QColor(0, 0, 0, 0))
                continue
            # Un-composite: recover the original colour from the white blend.
            scale = 255.0 / alpha
            ur = max(0, min(255, int((r - 255) * scale + 255)))
            ug = max(0, min(255, int((g - 255) * scale + 255)))
            ub = max(0, min(255, int((b - 255) * scale + 255)))

            # Neutral ink (the black wordmark) gets recoloured; the coloured
            # swoosh has a wide channel spread and passes through unchanged.
            if max(ur, ug, ub) - min(ur, ug, ub) < 45:
                ur, ug, ub = ink_colour.red(), ink_colour.green(), ink_colour.blue()

            image.setPixelColor(x, y, QColor(ur, ug, ub, alpha))

    return QPixmap.fromImage(image)


def _load_labs():
    import sys
    # Try both locations in order:
    # 1. Next to the exe (Nuitka standalone — sys.frozen is not set by Nuitka)
    # 2. Relative to this source file (dev mode)
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(sys.executable)), 'labs.json'),
        os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'core', 'labs.json')),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    raise FileNotFoundError("labs.json not found. Tried:\n" + "\n".join(candidates))


class ClickableCard(QFrame):
    """QFrame that behaves like a button — the whole surface is the hit area."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class CollegeSelectorWidget(QWidget):
    # Emits (college_name, app_name, url) when user picks a portal
    portal_selected = pyqtSignal(str, str, str)
    # Emitted when the user clicks Exit on the selector screen
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = _load_labs()
        self._current_college = None
        self._portal_grid = None
        self._portal_heading = None
        self._tiles = {}
        self._build_ui()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(f"CollegeSelectorWidget {{ background: {BG_PAGE}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_body(), 1)

    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("headerBar")
        bar.setFixedHeight(72)
        # Scoped by object name: QLabel derives from QFrame, so a bare QFrame
        # rule would draw the bottom border under the title text as well.
        bar.setStyleSheet(
            f"QFrame#headerBar {{ background: {BG_HEADER}; border: none;"
            f" border-bottom: 1px solid {BORDER}; }}"
        )

        row = QHBoxLayout(bar)
        row.setContentsMargins(36, 0, 28, 0)
        row.setSpacing(14)

        mark = QLabel("TP")
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {ACCENT}, stop:1 #0d5f68);
            color: #ffffff;
            border: 1px solid {GOLD};
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
            letter-spacing: 0.5px;
            font-family: {FONT};
        """)
        row.addWidget(mark)

        title = QLabel("Secure Exam Browser")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 19px; font-weight: 600;"
            f" letter-spacing: 0.2px; font-family: {FONT};"
        )
        row.addWidget(title)
        row.addStretch()

        exit_btn = QPushButton("⏻   Exit")
        exit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_DIM};
                border: 1px solid {BORDER_STRONG};
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 14px;
                font-weight: 600;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background: #5b1d1d; border-color: #b0472f; color: #ffffff; }}
            QPushButton:pressed {{ background: #7a2626; }}
        """)
        exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exit_btn.clicked.connect(self.exit_requested.emit)
        row.addWidget(exit_btn)

        return bar

    def _build_body(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG_PAGE}; border: none; }}
            QScrollBar:vertical {{ background: {BG_PAGE}; width: 10px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 5px; min-height: 40px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        page = QWidget()
        page.setStyleSheet(f"background: {BG_PAGE};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(56, 44, 56, 44)
        layout.setSpacing(0)

        heading = QLabel("Select your institution")
        heading.setStyleSheet(
            f"font-size: 34px; font-weight: 700; color: {TEXT};"
            f" letter-spacing: -0.4px; font-family: {FONT};"
        )
        layout.addWidget(heading)

        sub = QLabel("Choose an institution, then open the portal you have been assigned.")
        sub.setStyleSheet(f"font-size: 15px; color: {TEXT_MUTED}; font-family: {FONT};")
        layout.addWidget(sub)
        layout.addSpacing(30)

        inst_head, _ = self._section_header("🏛", "INSTITUTION")
        layout.addLayout(inst_head)
        layout.addSpacing(16)

        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(20)
        for college in self.config.get("colleges", []):
            tiles_row.addWidget(self._make_college_tile(college))
        tiles_row.addStretch()
        layout.addLayout(tiles_row)

        layout.addSpacing(34)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {BORDER}; border: none;")
        layout.addWidget(divider)

        layout.addSpacing(30)

        portal_head, self._portal_heading = self._section_header("🌐", "AVAILABLE PORTALS")
        layout.addLayout(portal_head)
        layout.addSpacing(18)

        grid_wrap = QWidget()
        grid_wrap.setStyleSheet("background: transparent;")
        self._portal_grid = QGridLayout(grid_wrap)
        self._portal_grid.setSpacing(22)
        self._portal_grid.setContentsMargins(0, 0, 0, 0)
        for col in range(3):
            self._portal_grid.setColumnStretch(col, 1)
        layout.addWidget(grid_wrap)

        layout.addStretch()

        scroll.setWidget(page)
        self._render_portals(None)
        return scroll

    def _section_header(self, glyph, text):
        """Gold section label preceded by a round glyph badge."""
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 0, 0, 0)

        badge = QLabel(glyph)
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {BG_CARD}; border: 1px solid {GOLD_DEEP};"
            f" border-radius: 17px; font-size: 15px;"
        )
        row.addWidget(badge)

        label = QLabel(text)
        label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {GOLD};"
            f" letter-spacing: 1.4px; font-family: {FONT};"
        )
        row.addWidget(label)
        row.addStretch()

        # The label comes back too, for sections that get retitled later.
        return row, label

    # ── College tiles ────────────────────────────────────────────────────────

    def _make_college_tile(self, college):
        tile = ClickableCard()
        tile.setObjectName("collegeTile")
        tile.setFixedSize(238, 196)

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(18, 14, 18, 20)
        layout.setSpacing(0)

        # Selected check badge, top-right
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.addStretch()
        check = QLabel("✓")
        check.setFixedSize(26, 26)
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setStyleSheet(
            f"background: {GOLD}; color: #21170a; border: none;"
            f" border-radius: 13px; font-size: 14px; font-weight: 700;"
            f" font-family: {FONT};"
        )
        check.hide()
        badge_row.addWidget(check)
        layout.addLayout(badge_row)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(84)
        logo.setStyleSheet("border: none; background: transparent;")

        path = _find_logo(college)
        pixmap = _logo_pixmap(path, 150, 84) if path else None
        if pixmap is not None:
            logo.setPixmap(pixmap)
        else:
            logo.setText(college[:2].upper())
            logo.setStyleSheet(
                f"border: none; background: transparent; font-size: 34px;"
                f" font-weight: 700; color: {ACCENT}; font-family: {FONT};"
            )
        layout.addWidget(logo)

        layout.addStretch()

        name = QLabel(college)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name)

        tile.clicked.connect(lambda c=college: self._on_college_clicked(c))
        tile._name_label = name
        tile._check = check
        self._tiles[college] = tile
        self._style_tile(tile, selected=False)
        return tile

    def _style_tile(self, tile, selected):
        if selected:
            tile.setStyleSheet(f"""
                QFrame#collegeTile {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {BG_CARD_SELECTED}, stop:1 {BG_CARD});
                    border: 2px solid {GOLD};
                    border-radius: 14px;
                }}
            """)
            colour, weight = TEXT, 700
        else:
            tile.setStyleSheet(f"""
                QFrame#collegeTile {{
                    background: {BG_CARD};
                    border: 1px solid {BORDER};
                    border-radius: 14px;
                }}
                QFrame#collegeTile:hover {{
                    background: {BG_CARD_HOVER};
                    border: 1px solid {BORDER_STRONG};
                }}
            """)
            colour, weight = TEXT_DIM, 600

        tile._check.setVisible(selected)
        tile._name_label.setStyleSheet(
            f"border: none; background: transparent; font-size: 17px;"
            f" font-weight: {weight}; letter-spacing: 0.4px; color: {colour};"
            f" font-family: {FONT};"
        )

    def _on_college_clicked(self, college):
        self._current_college = college
        for name, tile in self._tiles.items():
            self._style_tile(tile, selected=(name == college))
        self._render_portals(college)

    # ── Portal cards ─────────────────────────────────────────────────────────

    def _clear_grid(self):
        while self._portal_grid.count():
            item = self._portal_grid.takeAt(0)
            w = item.widget()
            if w:
                # Detach now — deleteLater alone leaves the old card painted
                # underneath the newly added ones until the event loop spins.
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _render_portals(self, college):
        self._clear_grid()

        if not college:
            self._portal_heading.setText("AVAILABLE PORTALS")
            self._portal_grid.addWidget(
                self._placeholder("Select an institution above to see its available portals."),
                0, 0, 1, 3,
            )
            return

        self._portal_heading.setText(f"AVAILABLE PORTALS   —   {college}")
        portals = self.config.get("portals", {}).get(college, [])
        if not portals:
            self._portal_grid.addWidget(
                self._placeholder(f"No portals are configured for {college}."), 0, 0, 1, 3
            )
            return

        columns = 3
        for idx, portal in enumerate(portals):
            card = self._make_portal_card(college, portal)
            self._portal_grid.addWidget(card, idx // columns, idx % columns)

    def _placeholder(self, text):
        box = QFrame()
        box.setStyleSheet(
            f"QFrame {{ background: transparent; border: 1px dashed {BORDER_STRONG};"
            f" border-radius: 12px; }}"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(26, 30, 26, 30)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"border: none; background: transparent; font-size: 14px;"
            f" color: {TEXT_MUTED}; font-family: {FONT};"
        )
        lay.addWidget(lbl)
        return box

    def _make_portal_card(self, college, portal):
        app_name = portal.get("app", "")
        url = portal.get("url", "")
        display_url = url.replace("http://", "").replace("https://", "")

        card = ClickableCard()
        card.setObjectName("portalCard")
        card.setMinimumWidth(300)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setStyleSheet(f"""
            QFrame#portalCard {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
            QFrame#portalCard:hover {{
                background: {BG_CARD_HOVER};
                border: 1px solid {ACCENT};
            }}
        """)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 90))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(0)

        # Icon + name/url
        head = QHBoxLayout()
        head.setSpacing(14)
        head.setContentsMargins(0, 0, 0, 0)

        icon = QLabel("🌐")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {ACCENT_SOFT}; border: 1px solid {BORDER_STRONG};"
            f" border-radius: 12px; font-size: 20px;"
        )
        head.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.setContentsMargins(0, 0, 0, 0)

        name_lbl = QLabel(app_name)
        name_lbl.setStyleSheet(
            f"border: none; background: transparent; font-size: 19px;"
            f" font-weight: 700; color: {TEXT}; font-family: {FONT};"
        )
        text_col.addWidget(name_lbl)

        url_lbl = QLabel(display_url)
        url_lbl.setWordWrap(True)
        url_lbl.setStyleSheet(
            f"border: none; background: transparent; font-size: 13px;"
            f" color: {TEXT_MUTED}; font-family: 'Consolas', 'Segoe UI', monospace;"
        )
        text_col.addWidget(url_lbl)

        head.addLayout(text_col, 1)
        layout.addLayout(head)

        layout.addSpacing(18)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {BORDER}; border: none;")
        layout.addWidget(divider)

        layout.addSpacing(16)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)

        tag = QLabel(college)
        tag.setStyleSheet(
            f"background: {ACCENT_SOFT}; color: {TEXT_DIM};"
            f" border: 1px solid {BORDER_STRONG}; border-radius: 6px;"
            f" padding: 5px 12px; font-size: 12px; font-weight: 700;"
            f" letter-spacing: 0.4px; font-family: {FONT};"
        )
        foot.addWidget(tag)
        foot.addStretch()

        open_btn = QPushButton("Open portal   →")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 11px 22px;
                font-size: 14px;
                font-weight: 600;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER}; }}
            QPushButton:pressed {{ background: #0d6068; }}
        """)
        open_btn.clicked.connect(
            lambda _checked, c=college, a=app_name, u=url: self.portal_selected.emit(c, a, u)
        )
        foot.addWidget(open_btn)
        layout.addLayout(foot)

        # The whole card stays clickable, not just the button.
        card.clicked.connect(
            lambda c=college, a=app_name, u=url: self.portal_selected.emit(c, a, u)
        )
        return card

    # ── Public API ────────────────────────────────────────────────────────────

    def show_selector(self):
        """Show the selector with no institution pre-selected."""
        for tile in self._tiles.values():
            self._style_tile(tile, selected=False)
        self._current_college = None
        self._render_portals(None)
        self.show()
        self.raise_()
