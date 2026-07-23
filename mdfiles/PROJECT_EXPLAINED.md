# Secure Exam Browser (TP‑Browser) — Full Project Documentation

> A plain‑English, question‑and‑answer walkthrough of the **whole** project.
> For every feature: *the problem we had* → *the solution we built* → *how the
> code actually works, line by line, in small pieces*.

---

## 0. What is this project, in one paragraph?

This is a **locked‑down web browser for online exams** (like Safe Exam Browser).
A student runs one `.exe`. The app takes over the screen, blocks cheating tools
(other browsers, screen recorders, Task Manager, virtual machines, debuggers),
shows a "pick your college / portal" screen, and then loads the exam website
full‑screen with the camera enabled for proctoring. It also updates itself and
lets the student fix their Wi‑Fi without leaving the locked environment.

**Tech stack:** Python + PyQt6 (Qt WebEngine = a real Chromium browser inside
our window) + Windows API calls via `ctypes`.

---

## 1. The big picture: how the program flows

```
main.py  (this is the entry point)
│
├─ Parent process ("launcher")
│    1. check_integrity()        → am I a real install, not tampered?
│    2. probe_environment()      → any debugger / VM running? (one-time)
│    3. enforce_single_instance()→ is another copy already running?
│    4. _check_for_updates_blocking() → check manifest; show updater if newer
│    5. launch_secure_desktop()  → create a NEW Windows desktop, run myself
│                                   again inside it with --secure-mode
│
└─ Child process ("--secure-mode", runs on the secure desktop)
     1. install_keyboard_hook()  → block Alt+Tab, Win key, Ctrl+Shift+Esc…
     2. ProcessSentinel.start()  → kill forbidden apps every minute
     3. anti_debug_loop()        → keep re-checking for debuggers/VMs
     4. start_proxy()            → local HTTP proxy for the camera trick
     5. SecureBrowser UI         → college selector → exam website
```

**Why split into two processes (parent + child)?**

- **Problem:** We want the exam to run on an isolated screen where Alt‑Tab and
  the normal desktop simply don't exist. But if we lock things down and the app
  crashes, the student's PC could be left broken.
- **Solution:** The **parent** stays on the normal desktop and acts as a
  safety net. It creates a brand‑new *Windows "secure desktop"* and launches a
  **child** copy of itself there. If the child dies, the parent's `finally`
  block switches back to the real desktop and calls `cleanup()` on the normal
  parent unwind path.
  The parent is basically the seatbelt.

---
## 2. `main.py` — the launcher and the two modes

### Q: Chromium camera flags must be set *before* Qt loads. How?

**Problem:** Qt WebEngine (Chromium) reads settings from an environment
variable `QTWEBENGINE_CHROMIUM_FLAGS` the *instant* the library loads. If you
set it after `import PyQt6`, it's already too late — the camera never works.

**Solution:** At the very top of `main.py`, *before any PyQt import*, if we're
in `--secure-mode` we set the env var immediately:

```python
if "--secure-mode" in sys.argv:
    from secure_browser.core.config import QT_FLAGS, ALLOWED_DOMAINS
    _origins = ",".join(f"http://{d}" for d in ALLOWED_DOMAINS)
    _flags = (f"{QT_FLAGS} "
              f"--unsafely-treat-insecure-origin-as-secure={_origins} "
              f"--user-data-dir=...SecureExamBrowserData")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags
```

`--unsafely-treat-insecure-origin-as-secure` is the key trick: browsers
normally only give camera access to `https://` sites. Our exam server is plain
`http://`, so we tell Chromium "trust these specific http addresses as if they
were secure."

### Q: How does the parent create a locked, separate screen?

**`launch_secure_desktop()`** uses raw Windows API through `ctypes`:

```python
h_desk = user32.CreateDesktopW("SecureExamDesktop", ...)  # a fresh empty desktop
sys_lock.toggle_task_mgr(disable=True)                    # kill Task Manager
success = kernel32.CreateProcessW(None, cmd, ...)         # launch child there
user32.SwitchDesktop(h_desk)                              # show that desktop
kernel32.WaitForSingleObject(pi.hProcess, INFINITE)       # wait for child
```

- A **Windows desktop** here is not "the folder with icons" — it's a security
  boundary. A window on `SecureExamDesktop` can't be Alt‑Tabbed to from the
  normal desktop, and vice‑versa.
 - `si.lpDesktop = "SecureExamDesktop"` tells `CreateProcessW` to start the
  child *on that desktop*.
- The `finally:` block **always** runs `user32.SwitchDesktop(original_desktop)`
  and `cleanup()`, so no matter how the exam ends, the student gets their real
  desktop and Task Manager back.

### Q: How does the app know whether it's the parent or child?

By a single command‑line flag:

```python
if "--secure-mode" in sys.argv:
    run_child_process()      # I'm the child on the secure desktop
else:
    launch_secure_desktop()  # I'm the parent launcher
```

### Q: What stops 5 double‑clicks from opening 5 heavy browsers?

**`enforce_single_instance()`** — a **named mutex** (a global OS lock):

```python
h_mutex = kernel32.CreateMutexW(None, False, "Global\\SecureExamBrowser_Mutex_2026_xYz")
if kernel32.GetLastError() == 183:   # 183 = ERROR_ALREADY_EXISTS
    return False                     # someone already holds the lock → quit
```

If the mutex already exists, another copy is running, so the new one exits
silently. The lock is released automatically by Windows if the app crashes.

### Q: How do we detect tampering / fake copies?

**`check_integrity()`** (only matters for the compiled `.exe`):

1. It checks that `python3*.dll` sits next to the `.exe`. Our build (Nuitka)
   always ships those DLLs. If someone copied *just* `main.exe` out of the
   install folder, the DLLs are missing → refuse to run.
2. It refuses to run from the Windows `TEMP` folder (a common trick to extract
   and bypass an installer).

### Q: The `cleanup()` safety net

```python
def cleanup():
    sys_lock.toggle_task_mgr(disable=False)   # re-enable Task Manager
    sys_lock.remove_keyboard_hook()           # remove key blocking
atexit.register(cleanup)                       # run on exit OR crash
```

`atexit` adds a best-effort cleanup path for normal interpreter shutdown and
many unhandled exceptions. It does not run after every hard process termination
or operating-system failure.

---

## 3. `security/system_locker.py` — blocking keyboard shortcuts & Task Manager

### Q: How do we stop Alt+Tab, the Windows key, and Ctrl+Shift+Esc?

**Problem:** A student could Alt+Tab to notes, press Win to open the Start menu,
or Ctrl+Shift+Esc to open Task Manager and kill the app.

**Solution:** A **low‑level keyboard hook** — Windows lets you install a
function that sees *every* key press before any app does, and you can "swallow"
keys by returning `1`.

```python
def hook_proc(self, nCode, wParam, lParam):
    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
    vk = kb.vkCode
    if vk in (91, 92):          # Left/Right Windows key
        return 1                 # 1 = "eat this key, don't pass it on"
    if alt_down and vk in (9, 27, 115, 32):   # Alt+Tab, Alt+Esc, Alt+F4, Alt+Space
        return 1
    if vk == 27 and ctrl_down and shift_down: # Ctrl+Shift+Esc (Task Manager)
        return 1
    return self.user32.CallNextHookEx(...)     # anything else → let it through
```

- `SetWindowsHookExW(WH_KEYBOARD_LL, callback, ...)` installs it.
- `self.callback_func = HOOKPROC(self.hook_proc)` — we **keep a reference** so
  Python's garbage collector doesn't delete the callback while Windows still
  points at it (a classic crash bug).

**Task Manager** is also disabled a second way, via the registry:

```python
key = winreg.CreateKey(HKEY_CURRENT_USER, r"...\Policies\System")
winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)  # 1=disable
```

Set to `1` at start, back to `0` on exit. Belt **and** suspenders: even if the
hook misses it, the registry flag stops Task Manager from opening.

---

## 4. `security/process_monitor.py` — killing forbidden apps

### Q: How do we stop other browsers, Zoom, screen recorders, etc.?

**Solution:** A background thread (`ProcessSentinel`) that walks the process
list once a minute and kills anything on the blocklist.

```python
class ProcessSentinel(threading.Thread):
    def run(self):
        while self.running:
            if not psutil.pid_exists(self.parent_pid):
                os._exit(1)          # parent died → child must die too
            for proc in psutil.process_iter(['pid', 'name']):
                name = (proc.info['name'] or '').lower()
                if name in self.target_apps:   # chrome.exe, obs64.exe, discord.exe…
                    proc.kill()
            time.sleep(59.0)
```

Key details:
- **`target_apps`** comes from `FORBIDDEN_APPS + SCREENSHOT_TOOLS` in
  `config.py` (Chrome, Firefox, Edge, Discord, TeamViewer, OBS, Snipping Tool…).
- **`process_cache`** remembers PIDs we already killed so we don't spam kills;
  it clears every 30s.
- **The parent‑alive check** is important: if the launcher dies, the child exits
  on its next scan. Because the loop sleeps for 59 seconds, that response is not
  instantaneous.
- It skips itself, its parent, and `python.exe` (so it doesn't kill itself
  during development).

---

## 5. `security/anti_debug.py` — anti‑debugging & anti‑VM

### Q: How do we stop someone reverse‑engineering the app or running it in a VM to cheat?

**Solution:** Detect debuggers (x64dbg, IDA, Wireshark, Cheat Engine…) and
virtual machines (VMware, VirtualBox, Hyper‑V), and refuse to run.

**Three detection methods:**

1. **Process names** — scan running processes for known tools. The names are
   stored **base64‑encoded** so you can't find them with `strings` on the
   `.exe`:
   ```python
   _B64_DBG_PROCS = ("Z2Ri", "eDY0ZGJn", ...)          # "gdb", "x64dbg" encoded
   _DEBUGGER_NAMES = tuple(_ds(s) for s in _B64_DBG_PROCS)  # decode at runtime
   ```

2. **Windows API** — `IsDebuggerPresent()` returns TRUE if a debugger is
   attached to our process:
   ```python
   if ctypes.windll.kernel32.IsDebuggerPresent():
       reasons.append("A debugger is attached...")
   ```

3. **Registry BIOS strings** — VMs leave fingerprints like "VMware" or
   "VirtualBox" in `HKLM\HARDWARE\...\BIOS`:
   ```python
   val, _ = winreg.QueryValueEx(key, "SystemManufacturer")
   if "vmware" in str(val).lower(): suspicious = True
   ```

**Two ways it runs:**
- `probe_environment()` — a **one‑time** check at startup. Returns
  `(ok, reasons)`. Non‑fatal; `main()` shows a message box and exits if not ok.
- `anti_debug_loop(60.0)` — runs forever in a background thread, re‑checking
  every ~60 seconds (with small random jitter so an attacker can't predict the
  timing) and hard‑exits via `_fatal_exit()` if a tool appears mid‑exam.

> Note: the MAC‑address VM check is deliberately **disabled** — installing
> VirtualBox on a real PC adds VM network adapters, which caused false
> positives on legitimate machines.

---

## 6. `network/login_proxy.py` — the local proxy (the camera trick)

### Q: Why do we need a proxy at all?

**Problem:** The exam login uses **face recognition** → it needs the camera.
Browsers block the camera on `http://` sites for security. Even with our
"treat‑as‑secure" flag, cross‑origin header issues remained.

**Solution:** Run a **tiny HTTP proxy on `127.0.0.1`** (localhost). The browser
talks to `http://127.0.0.1:<port>`, which browsers *do* treat as a secure
context, so the camera works. Our proxy quietly forwards every request to the
real exam server and rewrites the responses so the page thinks it's still
talking to itself.

### Q: How does the proxy work, step by step?

```python
def start_proxy() -> int:
    srv = ThreadedProxy((PROXY_HOST, 0), ProxyHandler)  # port 0 = OS picks free port
    _proxy_port = srv.server_address[1]
    _proxy_origin = f"http://127.0.0.1:{_proxy_port}"
    srv.serve_forever()   # in a background daemon thread
```

For each incoming request, `ProxyHandler._forward()`:

1. **Rebuilds the URL** to point at the real server (`_build_target_url`).
2. **Fixes headers** — sets `Host`, `Origin`, `Referer` to the real server so
   the exam backend accepts the request:
   ```python
   headers["Host"] = TARGET_NETLOC
   headers[k] = TARGET_ORIGIN          # for Origin
   ```
3. **Bypasses any system proxy** (`ProxyHandler({})`) so the internal exam IP is
   always reachable.
4. **Reads the response** and, for text (HTML/JS/JSON/CSS), **rewrites every
   mention** of the real server address back to the proxy address so links and
   AJAX calls stay inside the proxy:
   ```python
   text = text.replace(TARGET_ORIGIN, proxy_origin)     # http://server → http://127.0.0.1:port
   ```
   It handles tricky variants too: escaped slashes in JSON (`http:\/\/`),
   scheme‑relative `//host`, and HTML‑entity‑escaped URLs.
5. **Rewrites redirects and cookies** — strips `Domain=` and `Secure` from
   cookies so they stick to `127.0.0.1` over http (`rewrite_set_cookie`).
6. **Streams binary files** (images, video) straight through in 8 KB chunks —
   no rewriting, for speed.

### Q: What if the exam server is unreachable?

Instead of an ugly raw 502 error mid‑exam, the proxy sends a **friendly branded
HTML page** (`_send_error_page`) that says "This is usually a Wi‑Fi problem" and
has "Try Again" / "Network" buttons.

---

## 7. `network/request_signer.py` — signing every request (HMAC)

### Q: How does the exam server know a request really came from our browser?

**Problem:** Anyone could `curl` the exam server directly and cheat.

**Solution:** Every request gets three secret headers. `HmacRequestInterceptor`
runs inside Qt and stamps each outgoing request:

```python
timestamp = str(int(time.time()))
nonce = os.urandom(8).hex()                      # random, prevents replay
signature = hmac.new(secret_key, f"{timestamp}:{nonce}", sha256).hexdigest()
info.setHttpHeader(b"X-Exam-Time", timestamp)
info.setHttpHeader(b"X-Exam-Nonce", nonce)
info.setHttpHeader(b"X-Exam-Signature", signature)
```

The server has the same secret key and recomputes the signature — if it
matches and the timestamp is fresh, the request is genuine. Static files
(`.css`, `.js`, images) are skipped for speed (`_SKIP_TOKENS`).

### Q: Where is the secret key kept so it isn't visible in the `.exe`?

In `core/secrets.py` + `config.py`. The key is stored **encrypted** (Fernet)
and decrypted at runtime, so `strings app.exe` won't reveal it:

```python
APP_SECRET_KEY = decrypt(_APP_SECRET_KEY_ENC)   # decrypt on startup
```

The Fernet passphrase is itself split into parts (`"Tele","Secure","Exam"…`) so
the full string never appears as one literal. This is **obfuscation, not real
key management** (the code comments say so honestly) — a determined attacker
with the binary can still recover it.

---

## 8. `network/updater.py` + `ui/update_progress.py` — auto‑update

### Q: How does the app update itself?

**Flow:** `check_for_update()` → `download_installer()` → user clicks Install →
`launch_silent_install_and_relaunch()`.

1. **Check** — GET a JSON manifest from `UPDATE_CHECK_URL`:
   ```python
   payload = json.loads(raw)         # {"version": "1.1.0", "url": "..."}
   if _version_tuple(latest) > _version_tuple(APP_VERSION):
       return UPDATE_AVAILABLE, latest, url
   ```
   Only runs for the compiled `.exe` (`_is_frozen()`), never in dev mode.

2. **Download** — stream the new Inno Setup installer to a temp file.

3. **Install** — write a small `.bat` that waits 1 second, runs the installer
   **silently** (`/SILENT /SUPPRESSMSGBOXES /NORESTART`), relaunches the app,
   then deletes itself:
   ```python
   subprocess.Popen([bat_path], shell=True)
   os._exit(0)     # quit now so the installer can replace our files
   ```
   The batch script is used so the installer isn't trying to kill its own
   parent process while running.

The `UpdateProgressWindow` (a small Qt window) shows a spinner while
downloading and an "install" button when ready — the download runs on a
`QThread` so the UI doesn't freeze.

> **Known security note in the code:** there's **no checksum verification** — the
> manifest URL is trusted as‑is. If someone can spoof the update server they
> could push a malicious installer. This is flagged in the file's docstring to
> fix before wide rollout.

---

## 9. `network/wifi_manager.py` + `ui/dialogs.py` — Wi‑Fi inside the lockdown

### Q: The screen is locked. How does a student fix a dropped Wi‑Fi connection?

**Problem:** On the secure desktop there's no taskbar, so the normal Wi‑Fi menu
is gone. If the connection drops, the student is stuck.

**Solution:** A built‑in Wi‑Fi manager (the "📶 Network" toolbar button).

`WiFiManager` (backend, uses `pywifi` + Windows `netsh`):
- `scan_async()` — scans for networks on a background thread, emits
  `scan_complete` with the list (Qt signals keep the UI responsive).
- `get_saved_ssids()` — networks the PC already has passwords for → one‑click
  reconnect, no password prompt.
- `get_current_ssid()` — reads the connected network via
  `netsh wlan show interfaces` (shown on the toolbar button).
- `connect_async(ssid, password)` — builds a WPA2 profile and connects, waiting
  up to ~15s, then emits `connect_complete(success, message)`.

`WifiDialog` (the UI) lists networks (🔒 marks saved ones), asks for a password
only on new networks, and can reveal a saved password (`show_password`) — though
Windows only exposes it when running as Administrator.

---

## 10. `ui/college_selector.py` — pick college → pick portal

### Q: One app serves many colleges with different exam URLs. How?

**Solution:** A data‑driven two‑step selection screen loaded from `labs.json`.

- **Step 1:** a 2×2 grid of college cards (`_build_step1`).
- **Step 2:** after clicking a college, show its portal cards with a "Launch"
  button (`_populate_step2`).
- On Launch it emits a Qt signal with everything the browser needs:
  ```python
  self.portal_selected.emit(college, app_name, url)
  ```

`labs.json` shape:
```json
{
  "colleges": ["College A", "College B"],
  "portals": {
    "College A": [{"app": "Exam Portal", "url": "http://172.168.15.213"}]
  }
}
```

`_load_labs()` looks for `labs.json` next to the `.exe` first (production) then
in `core/` (dev), so it works both compiled and from source.

---

## 11. `ui/main_window.py` — the browser shell

This is the actual window the student sees. Key responsibilities:

### Q: How is it locked to full‑screen with no escape?

```python
self.setWindowFlags(FramelessWindowHint | Window | CustomizeWindowHint)
browser.showFullScreen()
```
Frameless = no minimize/close buttons. And `closeEvent` refuses to close unless
the student confirmed via "Exit Session":
```python
def closeEvent(self, event):
    if self._allow_close: event.accept()
    else: event.ignore()          # can't close by any other means
```

### Q: How is browsing restricted to only exam sites?

Two layers:
1. **`acceptNavigationRequest`** (in `browser_engine.py`) blocks any URL whose
   host isn't in `ALLOWED_DOMAINS` (or localhost/proxy). Typing google.com does
   nothing.
2. **`_build_url`** routes only the face‑login server through the local proxy
   (for the camera); everything else loads directly.

### Q: Camera permission — how is it auto‑granted?

`handle_permissions()` grants camera/mic **only** for allowed domains:
```python
if any(d in host for d in ALLOWED_DOMAINS):
    setFeaturePermission(..., PermissionGrantedByUser)
else:
    setFeaturePermission(..., PermissionDeniedByUser)
```

### Q: Extra in‑page hardening

`inject_security_js()` injects JavaScript into every loaded page to block:
- right‑click context menu,
- F12 / PrintScreen,
- Ctrl+Shift+I/J/C (DevTools shortcuts).

The clipboard is cleared immediately at startup and once more after a 500 ms
single-shot timer. It is not continuously cleared, and Ctrl+C/V/X remain
available for coding questions.

### Q: The "no internet" overlay

When a page fails to load (`loadFinished(False)`), a calm full‑screen card
appears with "Try Again" and "Network" buttons (`_build_offline_overlay`),
instead of Chromium's scary error page. It carefully ignores stale signals from
tabs that were just replaced, so it doesn't flash over a working page.

### Q: Tabs

The exam runs in a "home" tab that **cannot be closed** (`close_tab` blocks it).
The site can open extra tabs via `createWindow`, and those are closable.

---

## 12. `ui/browser_engine.py` — the Chromium page settings

`SecurePage` (extends `QWebEnginePage`) is where all the Chromium‑level
behavior is configured:

- **`_configure_settings()`** turns on LocalStorage, JS, plugins; allows insecure
  content and LAN WebRTC (needed for local‑network proctoring); sets the fake
  Linux/Chrome `USER_AGENT`.
- **`_inject_webrtc_monitor()`** wraps `navigator.mediaDevices.getUserMedia` with
  logging so we can debug camera issues (does the site ask? is it granted?).
- **`_try_grant_profile_permissions()`** pre‑grants camera/mic at the profile
  level on Qt 6.8+ so no popup ever appears; `_aggressively_grant` is the
  fallback for older Qt. The page-level fallback grants recognized media
  features immediately; `main_window.handle_permissions()` separately applies
  the configured domain check.
- **`certificateError()`** returns `True` — accepts self‑signed certs (the exam
  server uses them). Flagged in a comment as something to tighten later.

---

## 13. `core/config.py` — all the knobs in one place

Everything tunable lives here:
- `APP_VERSION`, `USER_AGENT`
- `APP_SECRET_KEY` (decrypted HMAC key)
- `UPDATE_CHECK_URL`, `TARGET_ORIGIN`, `TARGET_NETLOC`
- `ALLOWED_DOMAINS` — the whitelist of sites the browser may visit
- `FORBIDDEN_APPS` / `SCREENSHOT_TOOLS` — the kill list
- `QT_FLAGS` — the Chromium command‑line flags (camera, screen capture, GPU…)

> Important comment in the code: Chromium honors only **one**
> `--disable-features=` flag, so all disabled features are merged into a single
> comma‑separated list. Two separate flags = the first is silently ignored.

---

## 14. `core/logger.py` — logging that's free in production

A rotating file logger that is a **no‑op unless** `TELE_BROWSER_DEBUG=1` is set.
In production it uses a `NullHandler` with negligible overhead; in debug it writes to
`%TEMP%\SecureExamBrowser\secure_browser.log` (5 files × ~1 MB) and mirrors to
stderr.

---

## 15. Feature checklist (what's done)

| Feature | File(s) | Status |
|---|---|---|
| Secure isolated desktop | `main.py` | ✅ |
| Parent/child safety net + auto‑unlock | `main.py` | ✅ |
| Single‑instance lock | `main.py` | ✅ |
| Integrity / anti‑tamper check | `main.py` | ✅ |
| Keyboard lock (Alt+Tab, Win, etc.) | `system_locker.py` | ✅ |
| Task Manager disable | `system_locker.py` | ✅ |
| Kill forbidden apps & recorders | `process_monitor.py` | ✅ |
| Anti‑debug / anti‑VM (start + loop) | `anti_debug.py` | ✅ |
| Local proxy for HTTP camera | `login_proxy.py` | ✅ |
| HMAC request signing | `request_signer.py` | ✅ |
| Encrypted secret key at rest | `secrets.py` | ✅ |
| Auto‑update (download + silent install) | `updater.py`, `update_progress.py` | ✅ |
| In‑app Wi‑Fi manager | `wifi_manager.py`, `dialogs.py` | ✅ |
| College/portal selector (data‑driven) | `college_selector.py` | ✅ |
| Full‑screen locked browser + tabs | `main_window.py` | ✅ |
| Domain whitelist + camera auto‑grant | `browser_engine.py` | ✅ |
| In‑page anti‑cheat JS + clipboard clear | `main_window.py` | ✅ |
| Friendly offline / error pages | `main_window.py`, `login_proxy.py` | ✅ |

### Honest open items (flagged in the code itself)
- **Update channel is unauthenticated** (no checksum/signature) — `updater.py`.
- **Certificates are blindly accepted** — `browser_engine.py`.
- **Secret key is obfuscated, not truly secured** — `secrets.py`.
- **Update URLs are `http://`, not `https://`** — `config.py`.
- **Portal and allowlist drift is possible** — each host in `core/labs.json`
  must also be present in `ALLOWED_DOMAINS`; the current Google entry is not.

These are the natural "next steps" if you want to harden for a wide public
rollout.

---

## 16. Quick glossary for the tricky words

- **ctypes** — Python calling native Windows functions directly.
- **Hook** — a callback Windows runs for every key press before apps see it.
- **Mutex** — a named OS lock; only one holder at a time.
- **Proxy** — a middleman server; the browser talks to it, it talks to the real
  server.
- **HMAC** — a keyed signature proving a message came from someone who knows the
  secret key.
- **Fernet** — a simple symmetric encryption scheme (from the `cryptography`
  library).
- **QWebEngine** — Qt's embedded Chromium browser.
- **Secure desktop** — an isolated Windows screen, separate from the normal one.
