# `ui/` — User Interface Layer

The UI package contains the full-screen browser shell, the restricted
Qt WebEngine page, the data-driven college/portal selector, the Wi-Fi dialog,
and the launcher-side update window.

## Files at a glance

| File | Responsibility |
|---|---|
| `main_window.py` | Full-screen browser, toolbar, tabs, selector integration, offline overlay, and in-page restrictions |
| `browser_engine.py` | Navigation allowlist, WebEngine settings, media permissions, popups, and certificate handling |
| `college_selector.py` | Two-step college and portal selector populated by `core/labs.json` |
| `dialogs.py` | Modal Wi-Fi scan, connection, and saved-password UI |
| `update_progress.py` | Parent-launcher window for downloading and installing an available update |

## `main_window.py` — `SecureBrowser`

`SecureBrowser` is a frameless `QMainWindow` shown full-screen by the secure
child process. At construction it installs `HmacRequestInterceptor` on the
default WebEngine profile, creates the UI, clears the clipboard, reads the
current Wi-Fi SSID, and displays the college selector. It does not load a fixed
start URL.

### College and portal flow

- `CollegeSelectorWidget.portal_selected` is connected to
  `_on_portal_selected()`.
- Choosing a portal hides the selector, shows the navigation controls, clears
  old tabs safely, and creates a new non-closable home tab.
- `_build_url()` sends only URLs whose host exactly matches `TARGET_NETLOC`
  through the local proxy. Other permitted portal URLs load directly.
- **Change Portal** returns to the selector.

### Toolbar and tabs

The toolbar contains Back, Forward, Reload, Network/current SSID, active portal,
Change Portal, and Exit Session controls. Navigation controls remain hidden on
the selector screen. Toolbar buttons use `NoFocus` so Space or Enter inside an
exam does not accidentally activate them.

Every tab uses a `QWebEngineView` backed by `SecurePage`. The home exam tab and
the last remaining tab cannot be closed. Page popups are routed into additional
tabs, and tab titles are shortened to 30 characters.

### Load failures and offline recovery

`_on_load_finished()` shows a custom offline overlay when the current page fails
to load. It ignores queued signals from pages that were just removed, avoiding a
stale failure appearing over a working replacement tab. The overlay provides
Try Again and Network actions.

### UI-level restrictions

- The clipboard is cleared immediately and once more after a 500 ms single-shot
  timer. It is not cleared continuously.
- `handle_permissions()` grants requested features when the request host matches
  the configured allowlist and denies other hosts.
- After each load, `inject_security_js()` blocks the context menu, F12,
  PrintScreen, and Ctrl+Shift+I/J/C. Copy, cut, and paste remain available.
- `closeEvent()` refuses closure until the student confirms **Exit Session**.

### Wi-Fi integration

The Network button opens `WifiDialog`. After the dialog closes, the toolbar SSID
is refreshed. A successful connection also reloads the current page.

## `browser_engine.py` — `SecurePage`

`SecurePage` is the Chromium-level policy layer used by every browser tab.

### Navigation filtering

`acceptNavigationRequest()` allows:

- internal `about:`, `data:`, and `chrome:` schemes;
- `127.0.0.1` and `localhost` for the local proxy; and
- exact `ALLOWED_DOMAINS` hosts or their subdomains.

All other navigation is rejected. Because this check uses `ALLOWED_DOMAINS`,
every host listed in `core/labs.json` must also be added to that allowlist.

### Media and WebEngine configuration

- `_try_grant_profile_permissions()` uses the Qt 6.8+ profile permission API to
  pre-grant audio/video capture for each allowed HTTP and HTTPS origin.
- `_aggressively_grant()` is a page-level fallback that immediately grants the
  recognized audio, video, and desktop-capture features.
- `_inject_webrtc_monitor()` inserts a document-creation script that wraps
  `getUserMedia` and reports requests and results to the JavaScript console.
  `javaScriptConsoleMessage()` currently suppresses those console messages at
  the Python stderr boundary.
- Local storage, JavaScript, plugins, insecure content, local/remote URL access,
  autoplay, and LAN WebRTC candidates are enabled. The PDF viewer is disabled.
- The profile uses the configured user agent and an in-memory HTTP cache.

`createWindow()` sends popup requests back to `SecureBrowser.create_new_tab()`.
`certificateError()` currently accepts every certificate error to accommodate
self-signed exam infrastructure; this needs a trusted CA or pinning policy for
production.

## `college_selector.py` — `CollegeSelectorWidget`

`_load_labs()` searches for `labs.json` next to the running executable first,
then under the source `core/` directory. This allows an installed portal list to
be changed without rebuilding the executable.

The selector has two screens:

1. A grid of colleges from the `colleges` array.
2. Portal cards from `portals[college]`, each emitting
   `portal_selected(college, app_name, url)` when launched.

The installer copies `core/labs.json` to the installation directory beside
`SecureBrowser.exe`.

## `dialogs.py` — `WifiDialog`

The modal Wi-Fi dialog drives `network.wifi_manager.WiFiManager` through Qt
signals:

- it starts an asynchronous scan and displays sorted SSIDs;
- saved profiles are marked and reconnect without requesting a password;
- new networks prompt for a masked password;
- **Show Password** queries a saved Windows profile and normally requires
  elevation to reveal the key;
- closing the dialog cancels an in-progress scan; and
- successful connection accepts the dialog so the browser can reload.

## `update_progress.py` — `UpdateProgressWindow`

This small window runs only in the parent launcher, before the secure desktop is
created. `_DownloadWorker` downloads the Inno Setup installer on a `QThread`.
The progress bar is indeterminate because `download_installer()` does not expose
byte progress. When the download succeeds, an install button appears; clicking
it starts the detached silent-install/relaunch flow. A failed download closes
the window and normal launch continues.

## How the UI layer connects

- `main.py` creates `UpdateProgressWindow` only when a compiled build reports an
  available update.
- The secure child starts the proxy, constructs `SecureBrowser(proxy_origin)`,
  and shows it full-screen.
- `SecureBrowser` begins with `CollegeSelectorWidget`, then creates `SecurePage`
  tabs for the selected portal.
- The network layer signs requests, proxies the configured face-login host, and
  supplies the Wi-Fi and update operations used by the UI.
