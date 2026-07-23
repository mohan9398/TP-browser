# UI Brief — for handing to another LLM

Copy everything below the line into another model to get design proposals we
can actually implement. It states the stack, the hard constraints, the current
screens, and what to hand back.

---

## Project

A **secure exam browser** for Windows, used by engineering college students
(NGIT, KMIT, KMEC, KMCE) to take proctored online exams on lab PCs. It runs
full-screen on an isolated Windows desktop with Task Manager disabled and other
browsers killed. The student picks their college, picks a portal, and the exam
web app loads inside an embedded Chromium view.

Audience: 18–22 year old students, often stressed, on shared lab machines with
1366×768 to 1920×1080 screens. The brand owner's feedback was "make it look
more professional" — think enterprise/institutional software, not consumer app.

## Stack

- **Python 3.13 + PyQt6** (Qt 6 Widgets — the desktop widget toolkit, NOT QML,
  NOT Qt Quick).
- Styling is done with **QSS (Qt Style Sheets)**, set via `setStyleSheet()`.
- Layout is done with **Qt layout managers**: `QVBoxLayout`, `QHBoxLayout`,
  `QGridLayout` — not CSS.
- The exam content itself renders in **`QWebEngineView`** (embedded Chromium).
- Frameless, full-screen `QMainWindow`. No native title bar.
- Ships as a compiled Nuitka `.exe` + Inno Setup installer.

## HARD CONSTRAINTS — read carefully, most CSS advice does not apply

QSS is a **CSS 2.1-like subset**, not real CSS. Specifically:

- **No flexbox, no CSS grid, no `gap`, no `position`, no `float`, no `z-index`,
  no viewport units, no `calc()`, no CSS variables, no media queries.**
  Everything is positioned by Qt layout managers in Python code.
- **No `transition`, no `animation`, no `@keyframes`, no `transform`.**
  Animation only via `QPropertyAnimation` in Python.
- **No `box-shadow`.** Shadows only via `QGraphicsDropShadowEffect` in Python,
  and a widget can have only ONE graphics effect at a time.
- **No `::before` / `::after` content**, no pseudo-element icon tricks.
- **`border-radius` does not clip child widgets.** A rounded card with a
  full-bleed colored header strip will show square corners on the strip.
- Gradients only as `qlineargradient(...)` / `qradialgradient(...)`.
- Pseudo-states that DO work: `:hover`, `:pressed`, `:checked`, `:disabled`,
  `:focus`, `!selected`.
- A bare `QWidget` subclass ignores stylesheet backgrounds unless you set
  `WA_StyledBackground` or use `QFrame` instead.
- **Fonts: system-installed only.** The machines are offline/LAN-only, so no
  Google Fonts, no webfonts, no CDN. Safe choices are Segoe UI, Segoe UI
  Variable, Consolas, Cascadia Code. A custom font would have to be bundled and
  loaded with `QFontDatabase.addApplicationFont`.
- **No external assets at all** — offline LAN, no internet on exam day. Icons
  must be bundled files, drawn with QPainter, or Unicode/emoji glyphs (Segoe UI
  Emoji renders in color). SVG requires the QtSvg module.
- Must survive Windows display scaling at 100/125/150%.
- Dark mode is not required — single fixed theme is fine.

### Important alternative worth proposing

We already ship a full Chromium engine (`QWebEngineView`). A design *can* be
delivered as **plain self-contained HTML/CSS** and rendered in a web view for
the non-exam screens (college/portal picker, offline screen). That unlocks real
flexbox, transitions, and shadows. Trade-off: it needs a Python↔JS bridge
(`QWebChannel`) for click handling, and adds startup cost. **If your design
needs real CSS, say so explicitly and give the HTML/CSS** — we'll decide.
Otherwise keep every suggestion inside the QSS subset above.

## Current design (what exists today)

Palette: page `#f1f4f8`, header `#0f172a`, surface `#ffffff`, border `#dbe2ea`,
text `#0f172a`, muted `#64748b`, accent `#1d4ed8`. Font Segoe UI throughout.

### Screen 1 — Launcher / picker (the main one to redesign)

Single scrolling page:
1. Dark 64px app bar: blue rounded "TP" square mark, title "Secure Examination
   Browser", ghost "Exit" button far right (turns red on hover).
2. Page heading "Select your institution" + one-line subtitle.
3. Section label `INSTITUTION`, then a row of **4 small college boxes**
   (~132×62, white, 10px radius). They are toggle buttons; the selected one
   turns dark navy with white text.
4. Horizontal divider.
5. Section label `PORTALS · NGIT`, then the selected college's **portal cards**
   in a 3-per-row grid, appearing directly below the college boxes. Each card
   (288px wide, white, 12px radius, subtle shadow, blue border on hover) shows:
   portal name (e.g. "Test Center"), the raw URL in monospace, a divider, then a
   blue college tag pill and a blue `Open →` label. **The entire card is
   clickable** and launches the portal.
6. Before any college is picked, a dashed placeholder box says "Select an
   institution above to see its available portals."
7. Small version chip `v1.0.0` pinned bottom-left.

Data driving it (`labs.json`): 4 colleges; each has 2–3 portals with `app` name,
`slug`, and `url`. Portal names and count can change — the layout must handle
1 to ~8 cards per college. College count can grow to ~8.

### Screen 2 — Browser shell (after a portal opens)

60px white toolbar above a `QTabWidget`: Back / Forward / Reload / Wi-Fi buttons
(currently emoji + text labels), a blue "NGIT · Test Center" badge, then
"Change Portal" and a red "Exit Session" button on the right. Tabs are centered,
active tab is blue-tinted. Tabs are closable except the main exam tab.

### Screen 3 — Offline / error overlay

Centered white card on the page background: 📡 emoji, "Check your connection"
heading, a reassuring paragraph, and two buttons — outlined "Network" and solid
blue "Try Again".

Also exists: a Wi-Fi dialog and an update-download progress window.

## What I want back

1. A critique of the current design against "professional / institutional
   software" — be specific and blunt.
2. A concrete redesign of **Screen 1** first (it's what the boss sees), then
   Screens 2 and 3.
3. For each: exact hex colors, font sizes/weights, padding, margins, border
   radii, and fixed pixel sizes — I need numbers I can put straight into QSS.
4. A named color palette with roles (surface, border, text, muted, accent,
   danger, success).
5. Type scale (which sizes/weights for heading, card title, body, label, caption).
6. Hover/pressed/selected states for every interactive element, since QSS has no
   transitions — the states must read clearly as instant swaps.
7. An icon strategy that works offline (which glyphs, or "draw these with
   QPainter").
8. Call out anything in your proposal that CANNOT be done in QSS, and give the
   nearest QSS-legal fallback.

ASCII/box-drawing layout sketches are welcome. Do not give me React, Tailwind,
shadcn, or any web framework component — none of it applies here.
