# `ui/` — User Interface Layer

This folder builds everything the student actually **sees and interacts with**: the
full-screen exam window, the browser engine that renders the exam portal (with all
its security restrictions), and the Wi-Fi dialog. It is built on **PyQt6** and
**Qt WebEngine** (Chromium).

## Files at a glance

| File | Responsibility |
|------|----------------|
| `main_window.py` | The main full-screen browser window: toolbar, tabs, navigation, and security wiring. |
| `browser_engine.py` | The custom web page/engine that enforces domain rules, grants camera/mic, and restricts the page. |
| `dialogs.py` | The Wi-Fi management dialog shown from the toolbar. |

---

## `main_window.py` — `SecureBrowser` (the main window)

This is the top-level window the student uses during the exam.

**Window setup:**
- **Frameless, borderless window** (`FramelessWindowHint`) shown full-screen — no
  title bar, no minimise/close buttons, no way to resize or move it away.
- Installs the **HMAC request interceptor** (from the network layer) on the
  default WebEngine profile, so every request the browser makes is signed.
- Loads the exam start URL(s). If a **proxy origin** was passed in (it always is,
  in normal operation), it rewrites the start URL to route through the local
  proxy — keeping the browser on the trusted local origin.

**The toolbar (`create_toolbar`):**
A styled top bar with:
- **Back / Forward / Reload** navigation buttons.
- **Network** button → opens the Wi-Fi dialog.
- A **version label**.
- **Exit Session** button → asks for confirmation before allowing exit.

**Tabs (`create_new_tab`, `close_tab`, `update_tab_title`):**
- Supports multiple tabs, each a `QWebEngineView` backed by a `SecurePage`.
- The **home/exam tab cannot be closed** — attempting to close the last tab or
  the home tab shows an info box and is refused.
- Tab titles are taken from the page title and truncated to fit.

**Security behaviours wired here:**
- **`setup_clipboard_timer()`** — clears the system clipboard shortly after start,
  reducing the chance of pasting pre-prepared answers. (Ctrl+C/V/X themselves are
  intentionally *left enabled* for coding questions — see the injected JS.)
- **`handle_permissions()`** — grants camera/microphone/desktop-capture
  permissions, but **only for allowed domains**; everything else is denied.
- **`inject_security_js()`** — after every page load, injects JavaScript that:
  - Blocks the **right-click** context menu.
  - Blocks **F12** and **PrintScreen**.
  - Blocks **Ctrl+Shift+I / J / C** (DevTools shortcuts).
  - Deliberately **allows copy/paste/cut** so coding answers can be entered.
- **`confirm_exit()` + `closeEvent()`** — the window refuses to close unless the
  user explicitly confirms exit (`_allow_close` flag). This stops accidental or
  programmatic closure during an exam.

**`open_wifi()`** — opens the `WifiDialog`; if the student successfully connects,
the current page is reloaded.

---

## `browser_engine.py` — `SecurePage` (the locked-down web page)

`SecurePage` subclasses `QWebEnginePage` and is where the real browser-level
restrictions and capabilities live. Every tab uses one.

**Domain filtering (`acceptNavigationRequest`):**
- Internal schemes (`about:`, `data:`, `chrome:`) are allowed.
- Proxied localhost (`127.0.0.1`, `localhost`) is always allowed.
- External navigation is **only** permitted to domains in `ALLOWED_DOMAINS`
  (exact match or subdomain). Everything else is blocked — the student cannot
  surf away to other sites.

**Camera / microphone access (proctoring):**
The exam needs the webcam over plain HTTP, which Chromium normally forbids. This
class grants it through multiple layers for reliability:
- **`_try_grant_profile_permissions()`** — on Qt 6.8+, pre-grants camera/mic at
  the profile level for every allowed domain, so no prompt is ever shown.
- **`_aggressively_grant()`** — a per-page fallback (for older Qt) that grants any
  media permission the instant it is requested.
- **`_inject_webrtc_monitor()`** — injects JS at document creation that wraps
  `getUserMedia` to **log** every camera/mic request and whether it was granted —
  useful for diagnosing why a camera might not appear.

**Engine settings (`_configure_settings`):**
Enables local storage, JavaScript, plugins; allows insecure content and remote/
file access; allows LAN ICE candidates for WebRTC proctoring; sets the custom
user agent; and uses an in-memory HTTP cache (so stale "permission denied"
entries don't persist).

**Other behaviours:**
- **`createWindow()`** — routes any popup/`target=_blank` request into a new tab
  in the main window instead of a separate OS window.
- **`certificateError()`** — currently accepts SSL errors (the exam environment
  uses self-signed certs). *Marked as a TODO to tighten with cert pinning later.*
- **`javaScriptConsoleMessage()`** — a deliberate no-op that suppresses Chromium's
  default console spam to stderr.

---

## `dialogs.py` — `WifiDialog`

A modal dialog that lets the student manage Wi-Fi **without leaving the locked
browser**. It is the UI front-end for the network layer's `WiFiManager`.

- **Lists available networks** with a Refresh button; scanning runs asynchronously
  and shows an indeterminate progress bar while it works.
- **Connect** — prompts for a password (masked input) and connects on a background
  thread, again with a progress bar.
- Responds to the `scan_complete` and `connect_complete` Qt **signals** from
  `WiFiManager`, so the UI never freezes during scanning/connecting.
- On a successful connection it `accept()`s the dialog, which signals the main
  window to reload the exam page.

---

## How the UI layer ties together

- `main.py` (child process) builds the `QApplication` and a `SecureBrowser`,
  passing in the proxy origin, then shows it full-screen.
- `SecureBrowser` creates tabs, each backed by a `SecurePage` that enforces the
  domain/permission/restriction rules.
- The HMAC interceptor (network layer) signs requests; the proxy (network layer)
  is the origin pages load from.
- The Network toolbar button opens `WifiDialog`, which drives `WiFiManager`.

> **Note:** The window chrome is styled with Qt stylesheets for a clean, modern
> look, but the important parts are the **restrictions** layered on top of the
> standard browser behaviour.
