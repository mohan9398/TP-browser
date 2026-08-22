# TeleBrowser — Developer Reference

**Secure Exam Browser (Windows-only)**
Version in code: `1.0.1` (`core/config.py` → `APP_VERSION`)

Single-source developer reference for the whole project: what it is, how it's laid
out, how it starts up, each module, configuration, build/release, troubleshooting,
and the known risks to address before a wide rollout.

---

## 1. What this app is

TeleBrowser is a locked-down browser for online examinations. It runs only on
Windows and combines:

- **PyQt6 + Qt WebEngine (Chromium)** for the browser UI.
- **Windows APIs (ctypes)** for a separate secure desktop, a low-level keyboard
  hook, and Task Manager lockdown.
- **Local reverse proxies** so HTTP exam portals that need camera/mic access are
  treated as a secure origin by Chromium.
- **Security sentinels** — a forbidden-process killer and anti-debug / anti-VM checks.
- **Self-update** via a downloaded Inno Setup installer.

Core design idea: a **parent launcher** runs preflight checks, then spawns a
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
│   ├── config.py            # URLs, allowlists, proxy targets, Chromium flags, HMAC key
│   ├── labs.json            # Colleges → portals → URLs
│   ├── codec.py             # Fernet obfuscation-at-rest + anti-import guard
│   └── logger.py            # Opt-in rotating debug logger
├── network/
│   ├── localgw.py           # Multi-target local reverse proxy
│   ├── netheaders.py        # HMAC request interceptor (X-Exam-* headers)
│   ├── updater.py           # Update check / download / silent install
│   └── wifi_manager.py      # Async Wi-Fi scan/connect + SSID lookup
├── security/
│   ├── envprobe.py          # Debugger + VM detection
│   ├── watchdog.py          # Forbidden-process sentinel
│   └── wsession.py          # Keyboard hook + Task Manager registry policy
├── ui/
│   ├── main_window.py       # Full-screen browser shell (tabs, toolbar, overlays)
│   ├── browser_engine.py    # SecurePage: navigation + media-permission policy
│   ├── college_selector.py  # College/portal selection screen
│   ├── dialogs.py           # Wi-Fi dialog
│   └── update_progress.py   # Update download/install window
└── mdfiles/                 # Documentation (this file lives here)
```

**Packaging note.** All source imports use the package name `secure_browser`
(e.g. `from secure_browser.core.config import ...`), but the checkout folder is
named `TP-browser`. `build.py` creates a temporary NTFS directory junction
`secure_browser → TP-browser` at build time so Nuitka can import it. To run from
source, invoke it as a module from the **parent** folder (see §6).

---

## 3. Startup flow

### Parent launcher (`main.py`, normal desktop)

1. `check_integrity()` — frozen builds only: `python3*.dll` present, not running from `%TEMP%`.
2. `probe_environment()` — one-shot anti-debug / anti-VM check; hard-exits on hit.
3. `enforce_single_instance()` — named Windows mutex.
4. `_check_for_updates_blocking()` — frozen builds only; may exit and install.
5. `launch_secure_desktop()`:
   - Set `QTWEBENGINE_CHROMIUM_FLAGS` in the environment (inherited by the child).
   - `toggle_task_mgr(disable=True)`.
   - `CreateDesktopW("SecureExamDesktop")`.
   - `CreateProcessW(self, "--secure-mode")` on that desktop.
   - `SwitchDesktop()` → wait for the child → `SwitchDesktop` back → `cleanup()`.

### Child process (`run_child_process`, inside `SecureExamDesktop`, has `--secure-mode`)

1. `install_keyboard_hook()` — frozen builds only.
2. `ProcessSentinel().start()` — kills forbidden apps, watches the parent PID.
3. `anti_debug_loop(60s)` — background thread, hard-exits on hit.
4. `start_proxy()` — starts one proxy per `PROXY_TARGET_ORIGINS` entry; returns `{target_netloc: proxy_origin}`.
5. Inject Chromium flags into `sys.argv` (belt-and-suspenders).
6. `QApplication` + `SecureBrowser(proxy_routes).showFullScreen()`.

### Critical ordering rule

`QTWEBENGINE_CHROMIUM_FLAGS` **must** be set before *any* PyQt6 import — Chromium
reads it during the first Qt/WebEngine DLL load. It is therefore set in three
places for redundancy:

1. Top of `main.py` (when `--secure-mode` is present).
2. In `launch_secure_desktop()` before `CreateProcessW` (child inherits env).
3. Injected into `sys.argv` in `run_child_process()`.

### Fail-safe cleanup

`cleanup()` is registered with `atexit` and also called in the `finally` of
`launch_secure_desktop()`. It re-enables Task Manager and removes the keyboard
hook — this is what restores the machine if the app crashes.

---

## 4. Modules

### core/config.py

Central configuration. Key entries:

| Name | Purpose |
|---|---|
| `APP_VERSION` | `"1.0.1"` — UI badge, build metadata, updater comparison |
| `USER_AGENT` | Spoofed Chrome-on-Linux UA + `TeleBrowser/1.0` |
| `_APP_SECRET_KEY_ENC` | Fernet-encrypted HMAC key shipped in the binary |
| `get_app_secret_key()` | Decrypts the key on demand (no module global) — see §7 |
| `UPDATE_CHECK_URL` | `https://kmit.in/download` — update manifest endpoint |
| `PROXY_TARGET_ORIGINS` | Origins reached through the reverse proxy (one proxy each) |
| `TARGET_ORIGIN` / `TARGET_NETLOC` | Backwards-compat aliases = first entry of `PROXY_TARGET_ORIGINS` |
| `ALLOWED_DOMAINS` | Hosts allowed by `SecurePage.acceptNavigationRequest`; proxy hosts auto-appended |
| `FORBIDDEN_APPS` / `SCREENSHOT_TOOLS` / `ALL_BLOCKED_APPS` | Processes the sentinel kills |
| `QT_FLAGS` | Chromium media/security/WebRTC flags |

**`PROXY_TARGET_ORIGINS` rules** (most breakage comes from here):

- Each entry is an **origin only**: `scheme://host[:port]` — never a path.
- **Different ports are different servers** — list each separately
  (`http://10.11.52.100` and `http://10.11.52.100:541` are two entries).
- **Don't write `:80`** — use the bare host for port 80, because the browser
  reports the host without `:80` and the two must match.
- **Every entry needs a trailing comma.** A missing comma glues two strings into
  one invalid origin. Malformed entries are now skipped rather than fatal, but
  keep the list clean.

**Chromium flag gotcha.** Chromium honours only one `--disable-features=` flag —
the last one wins. All disabled features must live in a single comma-separated
list. This is already done; don't split it apart.

### core/codec.py

Fernet-based obfuscation-at-rest. The key is derived by SHA-256 over a passphrase
assembled from `_PARTS`. **This is obfuscation, not key management** — a
determined attacker with the binary can still recover the secret.

- `encrypt()` / `decrypt()` — the token codec used for `_APP_SECRET_KEY_ENC`.
- `_running_under_bare_python()` — the anti-import guard. Returns `True` only when
  a compiled `.pyd` build of this module is imported under a standalone
  `python.exe` (the copy-the-dist-and-dump attack); `decrypt()` refuses in that
  case. Dev runs (`.py` source) and the real packaged app (`SecureBrowser.exe`
  host) both pass. See §7.

### core/logger.py

Rotating logger, **disabled by default**. Turns on only when `TELE_BROWSER_DEBUG`
is truthy (`1/true/yes/on`). Logs to
`%TEMP%\SecureExamBrowser\secure_browser.log`, 5 files × ~1 MB. No-op otherwise.
Use `get_logger(__name__)`.

### network/localgw.py

Starts **one threaded HTTP reverse proxy per entry** in `PROXY_TARGET_ORIGINS`.

- `start_proxy(target_origins=None)` → returns `{target_netloc: proxy_origin}`,
  e.g. `{"10.11.36.18:81": "http://127.0.0.1:51234", ...}`. Each target binds its
  own `127.0.0.1:0` (OS-chosen) port. The map is also stored globally.
- `get_proxy_routes()` → the full map. `get_proxy_origin()` → first origin.
- Each proxy holds a `TargetContext` (its own upstream origin/scheme/netloc), so
  the header/cookie/URL-rewriting logic stays single-target simple.
- A malformed origin (e.g. from a missing comma) is **skipped**, not fatal.

Per-request behaviour:

- Forwards GET/POST/PUT/DELETE/OPTIONS to that proxy's target origin.
- Rewrites `Host`, `Origin`, `Referer` to the target.
- Buffers and rewrites **textual** responses so any target-origin reference
  (direct, escaped `\/`, scheme-relative `//host`, HTML-entity) points back at the
  proxy. Handles gzip/deflate/brotli (`Accept-Encoding: identity` requested).
- **Streams binary** responses (images/video) in 8 KB chunks without buffering.
- Rewrites `Location` redirects; strips `Domain=`/`Secure` from `Set-Cookie` so
  cookies stay host-only for `127.0.0.1`.
- Bypasses any system/OS proxy (`ProxyHandler({})`).
- On connection failure, serves a branded "Can't reach the exam server" 502 page
  unless the response already started.

**Why the proxy exists:** Chromium grants camera/mic only to **secure origins**.
The exam servers are plain HTTP. Serving them via `127.0.0.1` (always a secure
context) makes `getUserMedia` work. Only hosts in `PROXY_TARGET_ORIGINS` are
proxied; every other portal loads directly.

### network/netheaders.py

`HmacRequestInterceptor` (a `QWebEngineUrlRequestInterceptor`). On every
non-static request it adds:

- `X-Exam-Time` — unix timestamp.
- `X-Exam-Nonce` — 8 random bytes hex (anti-replay).
- `X-Exam-Signature` — `HMAC-SHA256(key, "timestamp:nonce")`.

The key comes from `config.get_app_secret_key()`, passed in at construction.
Static assets (`.css/.js/.png/...`, plus `theme`/`pluginfile`/`webservice`) are
skipped for performance. Installed once on the default profile in
`SecureBrowser.__init__`. Anti-replay only works if the exam server also checks
the timestamp and tracks used nonces.

### network/updater.py

Update flow (frozen builds only — `_is_frozen()` gates everything):

```
check_for_update() → download_installer() → [user clicks Install] → launch_silent_install_and_relaunch()
```

- Manifest is JSON `{ "version": "...", "url": "..." }` at `UPDATE_CHECK_URL`.
- Newer version compared via `_version_tuple` (dotted ints).
- Install writes a detached `.bat` that runs the installer
  `/SILENT /SUPPRESSMSGBOXES /NORESTART`, relaunches the app, deletes itself, then
  `os._exit(0)`.
- Fixed AppId in `installer.iss` → in-place upgrade of everything under `{app}`
  (including Cython `.pyd` files a single-exe swap would miss).
- **No checksum/signature verification** — see §8.

### network/wifi_manager.py

`WiFiManager(QObject)` wrapping `pywifi`. Signals `scan_complete(list)` and
`connect_complete(bool, str)`. Scans/connects on daemon threads.

- `get_saved_ssids()` — profiles already stored on the PC (one-click reconnect).
- `get_current_ssid()` — via `netsh wlan show interfaces` (no admin). Shown on the
  toolbar Wi-Fi button.
- `get_saved_password()` — `netsh ... key=clear`; **only works elevated**.
- New networks added as WPA2-PSK (or open if no password).
- `CREATE_NO_WINDOW` prevents a console flash on each `netsh` call.

### security/envprobe.py

Debugger and VM detection. Strings (debugger names, VM process names, VM markers,
registry paths) are base64-obfuscated and decoded at runtime.

- `probe_environment()` → `(ok, reasons)` — one process-list walk for both the
  debugger and VM lists; also `IsDebuggerPresent()` and VM registry markers. Used
  at startup (shows a message and exits on hit).
- `anti_debug_loop(interval=60)` — background thread; hard-exits (`_fatal_exit`)
  with a MessageBox on any hit. Adds small timing jitter.
- The MAC-prefix VM check is intentionally disabled — VirtualBox Host-Only
  adapters on a physical host caused false positives.
- `_fatal_exit()` shows a Windows MessageBox, then `os._exit(1)`.

### security/watchdog.py

`ProcessSentinel(threading.Thread)`. Every **59 seconds**:

- If the parent launcher PID no longer exists → `os._exit(1)` (child follows the
  parent).
- Kills any process whose name is in `ALL_BLOCKED_APPS`, skipping itself, its
  parent, and generic `python` processes.
- Caches killed PIDs, clears the cache every 30 s.

CMD/PowerShell/TaskMgr were removed from the kill list to avoid self-kill; Task
Manager is blocked via the registry instead. The 59 s interval is a wide blind
window between scans (see §8).

### security/wsession.py

`SystemLocker` (singleton `sys_lock`):

- `toggle_task_mgr(disable)` — sets `DisableTaskMgr` under `HKCU\...\Policies\System`.
- `install_keyboard_hook()` — low-level `WH_KEYBOARD_LL` hook blocking Win keys
  (L/R), Alt+Tab, Alt+Esc, Alt+F4, Alt+Space, Ctrl+Shift+Esc.
- `remove_keyboard_hook()` — must be called on exit (via `cleanup()`).
- Keeps a ref to the callback to prevent GC.

The keyboard hook installs **only in frozen/compiled builds** (`sys.frozen`), so
source runs don't trap your machine.

### ui/main_window.py

`SecureBrowser(QMainWindow)` — the full-screen shell.

- Frameless, full-screen, close guarded by `_allow_close` + `confirm_exit()`.
- Builds the HMAC interceptor from `get_app_secret_key()` and drops the key ref.
- Toolbar: Back / Forward / Reload / Network / college label / Change Portal /
  Exit. Buttons use `NoFocus` so Space/Enter don't fire a button instead of
  scrolling.
- Tabs (`QTabWidget`); the home/exam tab can't be closed.
- `create_new_tab()` wires `SecurePage`, permissions, titles, and
  `inject_security_js` (blocks right-click, F12, PrintScreen, Ctrl+Shift+I/J/C).
- `_build_url()` takes the portal URL, computes its `host[:port]`, and routes it
  through the matching proxy from `self.proxy_routes` (exact netloc match — no
  cross-port fallback). Hosts not in the map load directly. Requires a real
  `http://` scheme in the URL, or QUrl can't read the host and won't proxy.
- **Camera lifecycle:** `_clear_all_tabs()` destroys `QWebEngineView`s to release
  any active `getUserMedia` stream.
- Offline / college-selector overlays repositioned on resize.
- `_on_load_finished` ignores stale signals from replaced tabs.
- Clipboard cleared 500 ms after launch.
- `handle_permissions` grants media only to hosts matching `ALLOWED_DOMAINS`
  (substring match — see §8).

### ui/browser_engine.py

`SecurePage(QWebEnginePage)`:

- Injects a WebRTC monitor script logging `getUserMedia` + secure-context status.
- Enables LocalStorage, JS, plugins; disables the PDF viewer.
- WebRTC allows LAN ICE candidates (`WebRTCPublicInterfacesOnly=False`).
- Auto-grants media via three layers: Qt 6.8+ profile `setPermission`, the
  `featurePermissionRequested` signal, and `--use-fake-ui-for-media-stream`.
- `acceptNavigationRequest` — strict allowlist: internal schemes, localhost, and
  exact/`.`-suffix matches of `ALLOWED_DOMAINS`. Everything else blocked.
- `certificateError` → **returns True (accepts all)** — see §8.
- `javaScriptConsoleMessage` — no-op.

### ui/college_selector.py

`CollegeSelectorWidget` — the college/portal picker. Reads `labs.json` (next to
the exe first, then the source tree). Loads per-college logos from
`images/<college>-bg.<ext>`, drops the white JPEG background, and recolors the
wordmark for the dark card. Emits `portal_selected(college, app, url)` and
`exit_requested`.

### ui/dialogs.py

`WifiDialog(QDialog)` — scan list, saved networks marked and one-click reconnect,
password prompt for new networks, progress bar, cancels the scan on close. On
success it `accept()`s and the main window reloads.

### ui/update_progress.py

`UpdateProgressWindow` — shown by the **parent** only. Downloads on a `QThread`,
then reveals an Install button; clicking it calls
`launch_silent_install_and_relaunch` (does not return).

---

## 5. Configuration reference

### core/config.py — the file you'll edit most

- Add/remove portals in `core/labs.json`.
- **Every host used in `labs.json` must also be in `ALLOWED_DOMAINS`**, or
  `acceptNavigationRequest` blocks it. (Proxy target hosts are auto-appended.)
- To route a server through the proxy (camera over HTTP), add its **origin** to
  `PROXY_TARGET_ORIGINS`. Everything else loads directly.

### core/labs.json — colleges & portals

Shape (URLs **must** include `http://`):

```json
{
  "colleges": ["KMIT", "NGIT", "KMEC", "KMCE"],
  "portals": {
    "KMIT": [
      { "app": "Exam", "slug": "exam", "url": "http://10.11.36.18:81" }
    ]
  }
}
```

A portal `url` is proxied only if its `host[:port]` matches a
`PROXY_TARGET_ORIGINS` entry; otherwise it loads directly.

---

## 6. Development

Install dependencies:

```powershell
pip install -r requirements-build.txt
```

Run the **full** end-to-end app from the parent of the checkout (importable as
`secure_browser`):

```powershell
python -m secure_browser.main
```

Run the **UI only** for fast iteration (no secure desktop, sentinel, keyboard
hook, or update check; windowed and closable):

```powershell
python -m secure_browser.dev_run
```

Enable diagnostic logging:

```powershell
$env:TELE_BROWSER_DEBUG = "1"
python -m secure_browser.main
```

Source mode is intentionally safer than compiled: the keyboard hook and update
check only activate when `sys.frozen` is true, and the anti-import guard only
fires against compiled `.pyd` modules.

### Rotating the HMAC key

From the `TP-browser` folder:

```powershell
python -c "from core.codec import encrypt; print(encrypt('NEWKEY'))"
```

Paste the token into `_APP_SECRET_KEY_ENC` in `config.py`, and update the exam
server to use the same plaintext key.

---

## 7. Build & release

**Fast test build** (no LTO — ~5–15 min):

```powershell
python build.py --cython
```

**Final release build** (max protection, LTO — ~20–40 min, do not interrupt):

```powershell
python build.py --cython --harden
```

Build flags:

| Flag | Effect |
|---|---|
| (none) | Nuitka standalone only |
| `--cython` | Pre-compile sensitive modules to `.pyd` (also strips docstrings + build path) |
| `--lto` | Link-time optimization (smaller, much slower link) |
| `--harden` | Strip docstrings/asserts from non-Cython code, anti-bloat; implies `--lto` |
| `--debug` | Keep console, no version info |

Key facts:

- **Always `--standalone`, never `--onefile`.** The integrity check refuses to run
  from `%TEMP%` (where onefile extracts) and requires `python3*.dll` next to the
  exe.
- Output: `build/main.dist/SecureBrowser.exe` + supporting files. **Ship the entire
  `main.dist` folder.**
- The output exe name must be `SecureBrowser.exe` or `main.exe` (integrity check).
- Cython `.pyd` modules: `core/config.py`, `core/codec.py`, all of `security/`,
  `network/netheaders.py`, `network/localgw.py`. The Cython step sets
  `Options.docstrings = False` and passes a **relative** source path, so the
  `.pyd`s carry no docstrings and no `C:\Users\...` build path.
- `build.py` runs `purge_stale_artifacts()` **before** building and cleans
  `.pyd`/`.c` **after**, so an interrupted build can't poison the source tree.
- The build creates and removes a temporary `secure_browser` junction (no admin).
- College logos are bundled via `--include-data-dir=images=images`.
- The Nuitka step prints an ETA + timer and a "do not Ctrl+C" warning.

### Secret handling & the anti-import guard

Goal: make it non-trivial to pull the HMAC key out of the shipped build.

- The HMAC key has no module-level global. Callers use
  `config.get_app_secret_key()`, which decrypts on demand and drops the reference
  after use (`main_window` does `_key = get_app_secret_key(); ...; del _key`), so
  `import config; print(...)` no longer leaks it.
- `codec.decrypt()` and `get_app_secret_key()` call
  `codec._running_under_bare_python()` and **raise** if it returns `True`.
- How the guard decides:
  - Loaded from a `.py` file → **allow** (dev/source).
  - Compiled `.pyd` **and** the host is `python*.exe`/`py.exe` → **block** (the
    copy-the-dist-and-dump attack).
  - The real app is hosted by `SecureBrowser.exe` → **allow**.
- The plaintext fallback (`"my_production_secret_key_12345"`) is only returned for
  a genuinely broken crypto layer — never in the real app — and the guard's
  `RuntimeError` is deliberately not swallowed by it.

**Honest limit:** this stops a one-line `import` dump. It does not stop a
determined analyst who reads `_PARTS` + `_APP_SECRET_KEY_ENC` from the compiled
module and re-implements Fernet. The durable fix is server-issued per-session
tokens (not yet implemented). The guard depends on `sys.executable` being
`SecureBrowser.exe`; if a future packaging change makes it look like `python`,
loosen `_running_under_bare_python()` accordingly.

### Installer

Compile `installer.iss` with Inno Setup → `installer/TPBrowser_Setup_<version>.exe`.
Fixed AppId → clean in-place upgrades. **Reinstall (or run the dist exe directly)
after a rebuild** — the installed copy is not updated automatically.

---

## 8. Known risks & limitations

Address these before a wide/student rollout:

1. **`certificateError()` accepts ALL certificate errors** (`return True`). No
   pinning / trusted-CA. MITM is possible. (`ui/browser_engine.py`)
2. **Update installer is not verified.** No checksum/signature — anyone who can
   spoof `UPDATE_CHECK_URL` can run an arbitrary installer with admin rights.
   (`network/updater.py`)
3. **Most exam/portal endpoints are plain HTTP.** LAN traffic is unencrypted.
4. **HMAC key is a client-side shared secret.** Obfuscated and guarded, not
   provisioned; a determined analyst with the binary can still recover it. The
   durable fix is per-session server-issued tokens. A plaintext fallback still
   exists in `config.py` for the crypto-unavailable path.
5. **`--disable-web-security` and `--ignore-certificate-errors` are on** —
   deliberate (HTTP + cross-origin assets) but broaden the attack surface.
6. **`handle_permissions` uses a substring match** (`any(d in host ...)`) while
   `acceptNavigationRequest` uses strict exact/`.`-suffix matching. Make them
   consistent (prefer strict).
7. **The main exe leaks some plaintext constants** (e.g. IP addresses) because
   `ui/` and `main.py` are Nuitka-only, not Cython'd. Hiding these means
   Cythonizing the Qt UI (skipped — risky to compile).
8. **`except: pass` is pervasive.** Failures are swallowed; set
   `TELE_BROWSER_DEBUG=1` to see anything.
9. **Silent install depends on the machine's elevation policy.** If admin is
   blocked, the update fails quietly.
10. **`get_saved_password()` only works elevated.**
11. **`_fatal_exit` via `os._exit(1)`** skips `atexit` cleanup (the child is fine —
    the parent's `finally` restores state).
12. **Sentinel 59 s interval** is a wide blind window between scans.
13. **A stale `.pyd` in the source tree** (from an interrupted build) makes Python
    import it and the anti-import guard fire on normal `python` runs. Now guarded
    by `purge_stale_artifacts()` + the `finally` cleanup; if it recurs, delete
    `*.pyd`/`*.c` from `core/`, `security/`, `network/`.

---

## 9. Troubleshooting

| Symptom | Likely cause / check |
|---|---|
| App won't run from source: "secure runtime required" | Stale `.pyd` in `core/`/`security/`/`network/` from an interrupted build — delete `*.pyd`/`*.c` there |
| Built app won't open | Child crashed — read `Desktop\tp_crash.log`. Common: a bad `PROXY_TARGET_ORIGINS` entry, or an incomplete build (check `build\main.dist\python3*.dll` exists) |
| Build "takes forever" / never finishes | `--harden` enables LTO (one long link at the end). Use `python build.py --cython` for testing; only `--harden` for release, and don't Ctrl+C it |
| Camera not working on exam page | Host not in `PROXY_TARGET_ORIGINS` (so not a secure origin), or missing `http://` in the labs.json URL, or host missing from `ALLOWED_DOMAINS` |
| A portal isn't proxied | Its `host[:port]` doesn't exactly match a `PROXY_TARGET_ORIGINS` entry (ports must match; don't write `:80`); or the URL lacks `http://` |
| Blank page / "site blocked" | Host not in `ALLOWED_DOMAINS` → `acceptNavigationRequest` returned False |
| "Can't reach the exam server" page | Proxy could not reach that target — network/Wi-Fi issue |
| App closes with a security message | `probe_environment`/`anti_debug_loop` detected a debugger or VM process |
| App exits silently on launch | Single-instance mutex held, or integrity check failed (running from `%TEMP%` / missing `python3*.dll`) |
| Task Manager stays disabled after a crash | `cleanup()` didn't run; re-enable `HKCU\...\Policies\System\DisableTaskMgr = 0` |
| Logo missing on selector | No `images/<college>-bg.<ext>`, or `images/` not bundled |
| Nothing logged | `TELE_BROWSER_DEBUG` not set |

---

## 10. Glossary

- **Secure desktop** — a separate Windows desktop object (`SecureExamDesktop`) the
  child runs on; isolates it from the normal desktop's windows/input.
- **Proxy origin** — `http://127.0.0.1:<random port>`; the localhost address the
  browser talks to, which a proxy maps to one real exam server.
- **Proxy routes** — the `{target_netloc: proxy_origin}` map returned by
  `start_proxy()`; `_build_url()` uses it to send each portal to the right proxy.
- **Origin** — `scheme://host[:port]`. Different ports = different origins =
  different `PROXY_TARGET_ORIGINS` entries.
- **Frozen** — running as a compiled Nuitka exe (`sys.frozen`). Several protections
  (keyboard hook, update check, integrity check) are frozen-only.
- **Anti-import guard** — `codec._running_under_bare_python()`; blocks decrypting
  the key when the shipped `.pyd` is imported under a standalone `python.exe`.
- **Package-name bridge** — the temporary `secure_browser` junction that lets the
  code import itself by its canonical package name during builds/dev runs.
