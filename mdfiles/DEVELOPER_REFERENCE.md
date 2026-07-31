# TeleBrowser — Developer Reference

**Secure Exam Browser (Windows-only)**
Version in code: `1.0.1` (`core/config.py` → `APP_VERSION`)
Last documented: 2026-07-27

> This is a single-source developer reference for the whole project: architecture,
> module-by-module notes, configuration, build/release steps, the full startup
> flow, and a running list of known bugs / risks / TODOs. Paste directly into
> Google Docs.

---
 c
## 1. What this app is

TeleBrowser is a locked-down browser for online examinations. It runs only on
Windows and combines:

- **PyQt6 + Qt WebEngine (Chromium)** for the browser UI.
- **Windows APIs (ctypes)** for a separate secure desktop, a low-level keyboard
  hook, and Task Manager lockdown.
- **A local reverse proxy** so HTTP exam portals that need camera/mic access are
  treated as a secure origin by Chromium.
- **Security sentinels** — process killer, anti-debug/anti-VM checks.
- **Self-update** via a downloaded Inno Setup installer.

The core design idea: a **parent launcher** does preflight checks, then spawns a
**child process on an isolated Windows desktop** (`SecureExamDesktop`) with the
`--secure-mode` flag. The child is the actual browser.

---

## 2. Repository layout

```
TP-browser/
├── main.py                  # Parent/child orchestration, secure desktop, single-instance
├── dev_run.py               # Developer launcher (UI only, no lockdown)
├── build.py                 # Nuitka + Cython build driver
├── installer.iss            # Inno Setup installer definition
├── requirements-build.txt   # Runtime + build dependencies
├── Browser.ico / Browser.png
├── core/
│   ├── config.py            # URLs, allowlists, blocklists, Chromium flags, HMAC key
│   ├── labs.json            # Colleges → portals → URLs
│   ├── secrets.py           # Fernet obfuscation-at-rest for the embedded key
│   └── logger.py            # Opt-in rotating debug logger
├── network/
│   ├── login_proxy.py       # Local reverse proxy (127.0.0.1 → TARGET_ORIGIN)
│   ├── request_signer.py    # HMAC request interceptor (X-Exam-* headers)
│   ├── updater.py           # Update check / download / silent install
│   └── wifi_manager.py      # Async Wi-Fi scan/connect + SSID lookup
├── security/
│   ├── anti_debug.py        # Debugger + VM detection (obfuscated strings)
│   ├── process_monitor.py   # Forbidden-process sentinel
│   └── system_locker.py     # Keyboard hook + Task Manager registry policy
├── ui/
│   ├── main_window.py       # Full-screen browser shell (tabs, toolbar, overlays)
│   ├── browser_engine.py    # SecurePage: navigation + media-permission policy
│   ├── college_selector.py  # College/portal selection screen
│   ├── dialogs.py           # Wi-Fi dialog
│   └── update_progress.py   # Update download/install window
└── mdfiles/                 # Documentation (this file lives here)
```

**Important packaging note:** all source imports use the package name
`secure_browser` (e.g. `from secure_browser.core.config import ...`), but the
checkout folder is named `TP-browser`. `build.py` creates a temporary NTFS
directory junction `secure_browser → TP-browser` at build time so Nuitka can
import it. To run from source you must invoke it as a module from the **parent**
folder (see §7).

---

## 3. Runtime architecture & startup flow

```
main.py  (PARENT LAUNCHER — normal desktop)
  1. check_integrity()          # frozen builds only: python3*.dll present, not in %TEMP%
  2. probe_environment()        # one-shot anti-debug / anti-VM; hard-exit on hit
  3. enforce_single_instance()  # named Windows mutex (parent only)
  4. _check_for_updates_blocking()  # frozen builds only; may exit & install
  5. launch_secure_desktop():
        - set QTWEBENGINE_CHROMIUM_FLAGS in env (inherited by child)
        - toggle_task_mgr(disable=True)
        - CreateDesktopW("SecureExamDesktop")
        - CreateProcessW(self, "--secure-mode") on that desktop
        - SwitchDesktop() → wait for child → SwitchDesktop back → cleanup()

main.py  (CHILD — runs inside SecureExamDesktop, has --secure-mode)
  run_child_process():
        - install_keyboard_hook()   # frozen builds only
        - ProcessSentinel().start() # kills forbidden apps, watches parent PID
        - anti_debug_loop(60s)      # background thread, hard-exit on hit
        - start_proxy()             # binds 127.0.0.1:<random port>
        - inject Chromium flags into sys.argv (belt-and-suspenders)
        - QApplication + SecureBrowser(proxy_origin).showFullScreen()
```

### Critical ordering rule (do not break)
`QTWEBENGINE_CHROMIUM_FLAGS` **must** be set before *any* PyQt6 import. Chromium
reads it during the very first Qt/WebEngine DLL load. This is why
[main.py](../main.py) sets the env var at the very top of the file (lines ~10–24)
*before* importing PyQt6, and why [dev_run.py](../dev_run.py) does the same. The
flags are set in three places for redundancy:
1. Top of `main.py` (when `--secure-mode` present).
2. In `launch_secure_desktop()` before `CreateProcessW` (child inherits env).
3. Injected into `sys.argv` in `run_child_process()`.

### Fail-safe cleanup
`cleanup()` is registered with `atexit` and also called in the `finally` of
`launch_secure_desktop()`. It re-enables Task Manager and removes the keyboard
hook. This is what restores the machine if the app crashes.

---

## 4. Module-by-module notes

### core/config.py
Central configuration. Key entries:

| Name | Purpose / current value |
|---|---|
| `APP_VERSION` | `"1.0.1"` — used by UI badge, build metadata, updater comparison |
| `USER_AGENT` | Spoofed Chrome-on-Linux UA + `TeleBrowser/1.0` |
| `_APP_SECRET_KEY_ENC` / `APP_SECRET_KEY` | HMAC key, Fernet-encrypted at rest; **plaintext fallback** `"my_production_secret_key_12345"` if crypto layer fails |
| `UPDATE_CHECK_URL` | `https://kmit.in/download` — update manifest endpoint |
| `TARGET_ORIGIN` / `TARGET_NETLOC` | `http://172.168.15.213` — the face-login server reached through the proxy |
| `ALLOWED_DOMAINS` | Hosts allowed by `SecurePage.acceptNavigationRequest` |
| `FORBIDDEN_APPS` / `SCREENSHOT_TOOLS` / `ALL_BLOCKED_APPS` | Processes the sentinel kills |
| `QT_FLAGS` | Chromium media/security/WebRTC flags |

To rotate the HMAC key:
```powershell
python -c "from core.secrets import encrypt; print(encrypt('NEWKEY'))"
```
and paste the token into `_APP_SECRET_KEY_ENC`.

**Chromium flag gotcha:** Chromium honours only ONE `--disable-features=` flag —
the last one wins. All disabled features must be in a single comma-separated
list. This is already done; don't split it back apart.

### core/secrets.py
Fernet-based obfuscation-at-rest. The key is derived by SHA-256 over a passphrase
assembled from `_PARTS`. **This is obfuscation, not key management** — a
determined attacker with the binary can still recover the secret. `strings` on
the exe won't reveal it in plaintext, that's the whole benefit.

### core/logger.py
Rotating logger, **disabled by default**. Turns on only when env var
`TELE_BROWSER_DEBUG` is truthy (`1/true/yes/on`). Logs to
`%TEMP%\SecureExamBrowser\secure_browser.log`, 5 files × ~1 MB. No-op otherwise.
Use `get_logger(__name__)`.

### network/login_proxy.py
Threaded HTTP reverse proxy. `start_proxy()` binds `127.0.0.1:0` (OS picks a free
port) and returns the port; `get_proxy_origin()` returns `http://127.0.0.1:<port>`.

Responsibilities:
- Forwards GET/POST/PUT/DELETE/OPTIONS to `TARGET_ORIGIN`.
- Rewrites `Host`, `Origin`, `Referer` to the target.
- Buffers + rewrites **textual** responses (HTML/JS/JSON/CSS/XML) so any
  `TARGET_ORIGIN` reference — direct, escaped `\/`, scheme-relative `//host`, or
  HTML-entity-escaped — points back at the proxy. Handles gzip/deflate/brotli
  decompression (`Accept-Encoding: identity` is requested to minimize this).
- **Streams binary** responses (images/video) in 8 KB chunks without buffering.
- Rewrites `Location` redirects and strips `Domain=`/`Secure` from `Set-Cookie`
  so cookies stay host-only for `127.0.0.1`.
- Bypasses any system/OS proxy (`ProxyHandler({})`) — the target is a known LAN
  server; honoring a system proxy could make it unreachable.
- On connection failure, serves a branded "Can't reach the exam server" HTML
  page (502) instead of a raw error, unless the response already started.

Why the proxy exists at all: Chromium only grants camera/mic to **secure
origins**. The exam server is plain HTTP. Routing it through localhost + the
`--unsafely-treat-insecure-origin-as-secure` flag makes getUserMedia work.

### network/request_signer.py
`HmacRequestInterceptor` (a `QWebEngineUrlRequestInterceptor`). On every
non-static request it adds:
- `X-Exam-Time` — unix timestamp
- `X-Exam-Nonce` — 8 random bytes hex
- `X-Exam-Signature` — `HMAC-SHA256(APP_SECRET_KEY, "timestamp:nonce")`

Static assets (`.css/.js/.png/...`, plus `theme`/`pluginfile`/`webservice`)
are skipped for performance. Installed once on the default profile in
`SecureBrowser.__init__`.

### network/updater.py
Update flow (frozen builds only — `_is_frozen()` gates everything):
```
check_for_update() → download_installer() → [user clicks Install] → launch_silent_install_and_relaunch()
```
- Manifest is JSON `{ "version": "...", "url": "..." }` at `UPDATE_CHECK_URL`.
- Newer version compared via `_version_tuple` (dotted ints).
- Install is done by writing a detached `.bat` that runs the installer
  `/SILENT /SUPPRESSMSGBOXES /NORESTART`, relaunches the app, deletes itself,
  then `os._exit(0)`.
- Because `installer.iss` keeps a fixed AppId, this is an in-place upgrade of
  everything under `{app}` (including Cython `.pyd` files a single-exe swap
  would miss).
- **No checksum/signature verification** — see §8.

### network/wifi_manager.py
`WiFiManager(QObject)` wrapping `pywifi`. Signals `scan_complete(list)` and
`connect_complete(bool, str)`. Scans and connects run on daemon threads.
- `get_saved_ssids()` — profiles already stored on the PC (one-click reconnect).
- `get_current_ssid()` — static, via `netsh wlan show interfaces` (no admin
  needed). Shown on the toolbar Wi-Fi button.
- `get_saved_password()` — via `netsh ... key=clear`; **only works when running
  elevated**, else returns "".
- New networks are added as WPA2-PSK (or open if no password).
- `CREATE_NO_WINDOW` flag prevents a console flash on each `netsh` call.

### security/anti_debug.py
Non-fatal and fatal detection paths. Strings (debugger names, VM process names,
VM markers, registry paths) are **base64-obfuscated** and decoded at runtime.
- `probe_environment()` → `(ok, reasons)` — one process-list walk matching both
  debugger and VM lists; also `IsDebuggerPresent()` and VM registry markers.
  Used at startup (non-fatal, shows message + exits on hit).
- `anti_debug_loop(interval=60)` — background thread; hard-exits (`_fatal_exit`)
  with a MessageBox on any hit. Adds small timing jitter.
- **MAC-prefix VM check is intentionally disabled** — installing VirtualBox on a
  physical host creates Host-Only adapters and caused false positives.
- `_fatal_exit()` shows a Windows MessageBox explaining why, then `os._exit(1)`.

### security/process_monitor.py
`ProcessSentinel(threading.Thread)`. Every **59 seconds**:
- If the parent launcher PID no longer exists → `os._exit(1)` (child follows the
  parent, so closing the app tears everything down).
- Kills any process whose name is in `ALL_BLOCKED_APPS`, skipping itself, its
  parent, and generic `python` processes (unless explicitly forbidden).
- Caches killed PIDs, clears the cache every 30 s.

Note: CMD/PowerShell/TaskMgr were deliberately removed from the kill list to
avoid self-kill during dev/launch; Task Manager is blocked via registry instead.

### security/system_locker.py
`SystemLocker` (singleton `sys_lock`):
- `toggle_task_mgr(disable)` — sets `DisableTaskMgr` under
  `HKCU\...\Policies\System`.
- `install_keyboard_hook()` — low-level `WH_KEYBOARD_LL` hook blocking Win keys
  (L/R), Alt+Tab, Alt+Esc, Alt+F4, Alt+Space, and Ctrl+Shift+Esc.
- `remove_keyboard_hook()` — must be called on exit (done via `cleanup()`).
- Keeps a ref to the callback to prevent GC (crash otherwise).

**The keyboard hook only installs in frozen/compiled builds** (`sys.frozen`), so
source runs don't trap your machine.

### ui/main_window.py
`SecureBrowser(QMainWindow)` — the full-screen shell.
- Frameless, full-screen, close guarded by `_allow_close` + `confirm_exit()`.
- Toolbar: Back / Forward / Reload / Network / college label / Change Portal /
  Exit. Toolbar buttons use `NoFocus` so Space/Enter don't accidentally fire a
  button (e.g. Exit) instead of scrolling the page.
- Tabs (`QTabWidget`); the home/exam tab can't be closed.
- `create_new_tab()` wires `SecurePage`, permission handling, title updates, and
  `inject_security_js` (blocks right-click, F12, PrintScreen, Ctrl+Shift+I/J/C).
- `_build_url()` routes **only** `TARGET_NETLOC` through the proxy; all other
  URLs load directly.
- **Camera lifecycle:** `_clear_all_tabs()` destroys `QWebEngineView`s to tear
  down JS contexts and release any active `getUserMedia` stream — otherwise the
  camera stays on behind the next screen.
- Offline overlay + college-selector overlay are positioned on resize.
- `_on_load_finished` ignores stale signals from replaced tabs (avoids a false
  "no internet" overlay over a working page).
- Clipboard is cleared 500 ms after launch (`setup_clipboard_timer`).
- `handle_permissions` grants media only to hosts matching `ALLOWED_DOMAINS`
  (substring match — see §8).

### ui/browser_engine.py
`SecurePage(QWebEnginePage)`:
- Injects a WebRTC monitor script at document creation that logs
  `getUserMedia` calls and secure-context status (diagnostic).
- Enables LocalStorage, JS, plugins; disables PDF viewer.
- WebRTC set to allow LAN ICE candidates (`WebRTCPublicInterfacesOnly=False`).
- Auto-grants all media features via three layers: Qt 6.8+ profile-level
  `setPermission`, the `featurePermissionRequested` signal, and the
  `--use-fake-ui-for-media-stream` Chromium flag.
- `acceptNavigationRequest` — strict allowlist: internal schemes
  (`about/data/chrome`), localhost, and exact/`.`-suffix matches of
  `ALLOWED_DOMAINS`. Everything else is blocked.
- `certificateError` → **returns True (accepts all)** — see §8.
- `javaScriptConsoleMessage` — no-op to suppress Chromium console spam.

### ui/college_selector.py
`CollegeSelectorWidget` — the initial college/portal picker. Reads `labs.json`
(next to the exe first, then the source tree). Loads per-college logos from
`images/<college>-bg.<ext>`, drops the white JPEG background, and recolors the
black wordmark so it reads on the dark card. Emits `portal_selected(college,
app, url)` and `exit_requested`.

### ui/dialogs.py
`WifiDialog(QDialog)` — scan list, saved networks marked and one-click
reconnect, password prompt for new networks, progress bar, cancels the scan on
close. On success it `accept()`s and the main window reloads the page.

### ui/update_progress.py
`UpdateProgressWindow` — shown by the **parent** only. Downloads on a
`QThread`, then reveals an Install button; clicking it calls
`launch_silent_install_and_relaunch` (which does not return).

---

## 5. Configuration reference

### core/config.py — the file you'll edit most
- Change portals/URLs in `core/labs.json`.
- **Every host used in `labs.json` must also be permitted by `ALLOWED_DOMAINS`**,
  or `acceptNavigationRequest` blocks it.
- The proxy only applies to `TARGET_NETLOC`; other hosts load directly.

### core/labs.json — colleges & portals
Shape:
```json
{
  "colleges": ["NGIT", "KMIT", "KMEC", "KMCE"],
  "portals": {
    "NGIT": [ { "app": "Test Center", "slug": "testcenter", "url": "http://172.168.15.216:8000" }, ... ]
  }
}
```

---

## 6. Development

Install dependencies:
```powershell
pip install -r requirements-build.txt
```

Run the **full** end-to-end app from the parent of the checkout (needs the
`secure_browser` package name):
```powershell
# from the folder that CONTAINS TP-browser, with TP-browser importable as secure_browser
python -m secure_browser.main
```

Run the **UI only** for fast iteration (no secure desktop, no sentinel, no
keyboard hook, no update check, windowed & closable):
```powershell
python -m secure_browser.dev_run
```

Enable diagnostic logging:
```powershell
$env:TELE_BROWSER_DEBUG = "1"
python -m secure_browser.main
```

Source-mode is intentionally safer than compiled: the keyboard hook and update
check only activate when `sys.frozen` is true.

---

## 7. Build & release

Recommended production build (maximum protection):
```powershell
python build.py --cython --harden
```
Build flags:
| Flag | Effect |
|---|---|
| (none) | Nuitka standalone only |
| `--cython` | Pre-compile sensitive modules to `.pyd` before Nuitka (recommended) |
| `--lto` | Link-time optimization (smaller, slower build) |
| `--harden` | Strip docstrings/asserts, anti-bloat; implies `--lto` |
| `--debug` | Keep console, no version info |

Key build facts:
- **Always `--standalone`, never `--onefile`.** The integrity check refuses to
  run from `%TEMP%` (where onefile extracts) and requires `python3*.dll` next to
  the exe.
- Output: `build/main.dist/SecureBrowser.exe` + supporting files. **Ship the
  entire `main.dist` folder**, not just the exe.
- Output exe name must be `SecureBrowser.exe` or `main.exe` — the integrity check
  only accepts those basenames.
- Cython modules compiled to `.pyd`: `core/config.py`, `core/secrets.py`, all of
  `security/`, `network/request_signer.py`, `network/login_proxy.py`. Generated
  `.pyd`/`.c` files are cleaned from the source tree after the build.
- The build creates and removes a temporary `secure_browser` junction (no admin
  needed).
- College logos are bundled via `--include-data-dir=images=images`.

Installer:
```
Compile installer.iss with Inno Setup → installer/TPBrowser_Setup_<version>.exe
```
Fixed AppId → clean in-place upgrades.

---

## 8. Known bugs, risks & TODOs

### Data / config bugs
1. **`ALLOWED_DOMAINS` contains a full URL, not a host:**
   `"https://elms.kmce.in/download"`. Since flags build origins as
   `http://<entry>`, this yields the malformed origin
   `http://https://elms.kmce.in/download`. It should be a bare host like
   `elms.kmce.in`. (`core/config.py`)
2. **Google portal is unreachable.** `labs.json` lists
   `http://www.google.com` for NGIT, but `google.com`/`www.google.com` is **not**
   in `ALLOWED_DOMAINS`, so `acceptNavigationRequest` blocks it. Either add the
   host or remove the portal.
3. **Version mismatch in docs vs code.** Code is `APP_VERSION = "1.0.1"`; the
   top-level `README.md` and installer references still say `1.0.0`. Keep them in
   sync when bumping.

### Security risks (must address before wide/student rollout)
4. **`certificateError()` accepts ALL certificate errors** (`return True`). No
   pinning or trusted-CA policy. MITM is possible. (`ui/browser_engine.py:155`)
5. **Update installer is not verified.** No checksum/signature check — anyone who
   can spoof `UPDATE_CHECK_URL` traffic can execute an arbitrary installer with
   admin rights on every machine that checks in. (`network/updater.py`)
6. **All exam/portal/update endpoints are plain HTTP** (except the update URL
   which is HTTPS but points at a dev host). LAN traffic is unencrypted.
7. **HMAC key is obfuscated, not provisioned.** A plaintext fallback
   (`"my_production_secret_key_12345"`) is compiled in. Recoverable from the
   binary. Provision per-deployment from a server for real protection.
8. **`--disable-web-security` and `--ignore-certificate-errors`** are on. These
   are deliberate (HTTP + cross-origin exam assets) but broaden the attack
   surface considerably.
9. **`handle_permissions` uses a substring match** (`any(d in host ...)`), so a
   host like `evil-172.168.15.213.example.com` could satisfy an allowlist entry.
   `acceptNavigationRequest` uses stricter exact/`.`-suffix matching — the two
   should be made consistent (prefer the strict form).

### Robustness / minor
10. **Bare `except: pass` is pervasive** (cleanup, hooks, proxy, anti-debug).
    Failures are swallowed silently; set `TELE_BROWSER_DEBUG=1` to see anything.
    Consider routing these through the logger.
11. **`login_proxy.py` parse fallback is incomplete** — if
    `urlsplit(TARGET_ORIGIN)` throws, only `TARGET_SCHEME` is set and
    `TARGET_HOST`/`TARGET_PORT` are left undefined. Harmless with the current
    hard-coded target but fragile.
12. **Silent install still depends on the machine's elevation policy.** If the
    installer needs admin and the exam machine blocks it, the update fails
    quietly.
13. **`get_saved_password()` only works elevated.** On non-admin machines saved
    Wi-Fi passwords can't be read (connect via saved profile still works).
14. **`_fatal_exit` via `os._exit(1)`** skips `atexit` cleanup. In the child this
    is fine (parent's `finally` restores state), but be aware Task Manager /
    keyboard-hook restoration relies on the parent surviving.

---

## 9. Quick troubleshooting

| Symptom | Likely cause / check |
|---|---|
| Camera not working on exam page | Page not routed through proxy, or host missing from `ALLOWED_DOMAINS`; check `QTWEBENGINE_CHROMIUM_FLAGS` set before Qt import; check console for the injected `[INJECTED JS]` logs |
| Blank page / "site blocked" | Host not in `ALLOWED_DOMAINS` → `acceptNavigationRequest` returned False |
| "Can't reach the exam server" page | Proxy could not reach `TARGET_ORIGIN` — network/Wi-Fi issue |
| App closes immediately with a security message | `probe_environment` / `anti_debug_loop` detected a debugger or VM process; close VM tools / debuggers |
| App exits silently on launch | Single-instance mutex already held (another launcher running), or integrity check failed (running from `%TEMP%` or missing `python3*.dll`) |
| Task Manager stays disabled after a crash | `cleanup()` didn't run; re-enable `HKCU\...\Policies\System\DisableTaskMgr = 0` manually |
| Logo missing on selector | No `images/<college>-bg.<ext>`, or `images/` not bundled in the build |
| Nothing logged | `TELE_BROWSER_DEBUG` not set — logging is a no-op by default |

---

## 10. Glossary of the non-obvious

- **Secure desktop** — a separate Windows desktop object (`SecureExamDesktop`)
  the child runs on; isolates it from the normal desktop's windows/input.
- **Proxy origin** — `http://127.0.0.1:<random port>`; the localhost address the
  browser actually talks to, which the proxy maps to the real exam server.
- **Frozen** — running as a compiled Nuitka exe (`sys.frozen`), vs. running from
  Python source. Several protections (keyboard hook, update check, integrity
  check) are frozen-only by design.
- **Package-name bridge** — the temporary `secure_browser` junction that lets the
  code import itself by its canonical package name during builds/dev runs.
```
