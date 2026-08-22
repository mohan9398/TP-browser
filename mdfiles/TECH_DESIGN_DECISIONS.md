# TeleBrowser (TP-Browser) — Technology & Design Decisions

## 1. Project Overview

TeleBrowser (TP-Browser) is a Windows-only, locked-down secure exam browser for
conducting online examinations. Its purpose is to present an approved exam portal
to a student while preventing cheating — blocking other applications, keyboard
shortcuts, screen capture, remote-access tools, and virtual machines, while
enforcing a controlled network path with request signing and camera/microphone
support.

Because the product is essentially "a browser we fully control," every technology
choice was made around a single question:

> **How do we render a real web exam portal while keeping total control over the
> machine, the process, and the network?**

---

## 2. Core Technology Choices

### 2.1 Python 3.13 — Primary Language

| Reason | Detail |
|---|---|
| Windows API access | Direct low-level calls via `ctypes` and `pywin32` |
| Rich ecosystem | Mature libraries: `psutil`, `pywifi`, `cryptography` |
| Native compilation | Secure distribution via Nuitka + Cython into a native binary |
| Development speed | Rapid integration of complex Windows subsystems (process scanning, registry edits) |

### 2.2 PyQt6 — Application Framework & UI

**Why chosen:** PyQt6 delivers a native desktop shell and a bundled Chromium
engine (via PyQt6-WebEngine / Qt WebEngine) in one framework — no need to bolt a
browser onto a separate UI toolkit.

**Key capabilities leveraged:**

| Capability | What it enables |
|---|---|
| Kiosk windows | Frameless, always-on-top, full-screen shell |
| `QWebEngineUrlRequestInterceptor` | Signs every request (HMAC headers) + filters navigation |
| `QWebEnginePage` subclass (`SecurePage`) | Per-domain allow/deny, `certificateError()` override, JS dialog control |
| `featurePermissionRequested` | Grants camera/mic only to approved origins |
| `QWebEngineProfile` | Injects Chromium flags + custom user agent |
| Native Qt widgets | Portal selector, Wi-Fi dialog, update window — all inside the controlled desktop |
| Signals/slots + threading | Async Wi-Fi scans and update downloads without freezing the UI |

**Alternatives rejected:**

| Option | Why rejected |
|---|---|
| Electron / raw CEF | Chromium but no native Windows shell; heavy Node.js/JS stack; weaker Win32 access |
| Tkinter / wxPython | No built-in modern browser engine |
| WebView2 (Edge) | Tied to Edge's update cadence; less control over request interception and flags |

### 2.3 Chromium — Rendering Engine

**Why chosen:**

- **Real-world compatibility** — exam portals are built and tested against Chrome;
  the same Blink/V8 engine guarantees identical rendering (WebRTC, `getUserMedia`,
  modern JS).
- **Flag-level configurability** — Chromium switches passed via `QT_FLAGS` in
  `core/config.py` tune media, security, GPU, and WebRTC behavior.
- **Per-origin permission model** — auto-grants camera/mic to approved exam
  origins, denies everything else.

> ⚠️ **Design constraint:** Chromium honors only one `--disable-features=` switch,
> so all disabled features must be a single comma-separated list. Documented
> directly in `core/config.py` to prevent future breakage.

---

## 3. Feature Implementation

### 3.1 Secure Launch & Desktop Isolation

Two-process model: the parent launcher runs preflight checks and creates an
isolated `SecureExamDesktop`. Running the exam on a dedicated Windows desktop
object shields it from background apps and overlays.

### 3.2 Data-Driven Lockdown

The first screen is driven by `core/labs.json` (colleges → portals → URLs). One
binary serves many institutions — adding a college is a JSON edit, not a code
change.

### 3.3 Desktop & Keyboard Lockdown — `security/wsession.py`

Disables Task Manager and installs low-level keyboard hooks to block Alt+Tab,
Alt+F4, etc.
**Safety design:** hooks are installed only in the compiled build (`sys.frozen`),
so developers running from source don't lock themselves out.

### 3.4 Process Sentinel — `security/watchdog.py`

Scans processes ~every 59 seconds and terminates a configured blocklist: other
browsers, comms tools (Discord, Slack, Zoom, Telegram), remote-desktop clients
(AnyDesk, TeamViewer), and screen-capture tools (OBS, ShareX, Snipping Tool).
Lists live in `core/config.py` (`FORBIDDEN_APPS`, `SCREENSHOT_TOOLS`).

### 3.5 Anti-Debug & Anti-VM — `security/envprobe.py`

Detects virtual environments and debuggers to discourage bypass attempts.

### 3.6 Local Reverse Proxy — `network/localgw.py`

Binds a random localhost port, forwards to a target origin (face-login server),
rewrites text payloads/redirects/cookies, and streams binary responses. Makes a
remote HTTP origin appear same-origin/localhost so camera/mic permissions work.
One bad `PROXY_TARGET_ORIGINS` entry is now skipped rather than crashing the app.

### 3.7 HMAC Request Signing — `network/netheaders.py`

A `QWebEngineUrlRequestInterceptor` adds `X-Exam-Time`, `X-Exam-Nonce`, and
`X-Exam-Signature` headers to non-static requests, keyed by the app secret, so
the server can reject forged/replayed calls.

### 3.8 Secret-Key Obfuscation — `core/codec.py`, `core/config.py`

HMAC key stored encrypted at rest (Fernet token), decrypted at runtime, so it
isn't plaintext in the compiled binary. The key is fetched **on demand** via
`get_app_secret_key()` (no longer a module-level global) and dropped after use.
A plaintext fallback keeps the app running if the crypto layer is genuinely
unavailable. See 3.13 for the reverse-engineering hardening around this.

### 3.9 Camera & Microphone Support — `ui/browser_engine.py`

Chromium/Qt media flags + per-origin `featurePermissionRequested` auto-grant
camera/mic to approved proctoring origins.

### 3.10 Built-in Wi-Fi Management — `network/wifi_manager.py`, `ui/dialogs.py`

Via `pywifi`, students scan, reconnect to saved networks, and join new WPA2/open
networks without leaving the secure desktop — a dropped connection doesn't force
them out.

### 3.11 Installer-Based Updates — `network/updater.py`, `ui/update_progress.py`

Compiled builds check a JSON manifest (`UPDATE_CHECK_URL`), download an Inno Setup
installer in the background, and run it on user confirmation.

### 3.12 Single-Instance Enforcement

A named Windows mutex prevents two launchers running simultaneously.

### 3.13 Reverse-Engineering Resistance & Anti-Tamper Hardening — *(the RE work)*

**Why this exists:** the compiled build was formally assessed for how well it
resists reverse engineering. A dedicated pass (**Ghidra headless decompilation of
all seven Cython `.pyd` modules → static string/data analysis → per-module logic
review by a local LLM**) was run against the shipped dist and written up in
[`RE_ASSESSMENT.md`](../RE_ASSESSMENT.md). The verdict framed the whole design
decision:

> The `--cython --harden` build is **effective against casual/static reverse
> engineering but not against a determined analyst.** `strings`/`rabin2`/FLOSS
> recover no config, IPs, URLs, or key material (Cython string compression keeps
> them out of naive tooling), but the obfuscation is reversible dynamically — and
> a **client-held HMAC secret can never be made truly safe by client obfuscation
> alone.** Mean static-RE resistance ≈ **6.4/10** ("moderate").

That assessment drove a concrete, **already-implemented** set of hardening
changes — the "RE thing":

| # | Hardening (implemented) | Where | What it defeats |
|---|---|---|---|
| 1 | **Bare-Python import guard** — `decrypt()` refuses to run when the compiled `.pyd` is imported under a standalone `python.exe` | `core/codec.py` (`_running_under_bare_python()`) | The one-line "copy the dist and `python -c "import ...; decrypt(...)"`" key-dump attack |
| 2 | **Secret no longer a module global** — key fetched on demand via `get_app_secret_key()` and `del`'d after building the interceptor | `core/config.py`, `ui/main_window.py` | `import config; print(config.APP_SECRET_KEY)` no longer leaks the key |
| 3 | **Docstring stripping in Cython** — `Options.docstrings = False` at compile time | `build.py` (`compile_cython_modules`) | `strings module.pyd` no longer reveals `encrypt`/`decrypt`/"Decrypt a token produced by encrypt()…" — removes the attacker's *map* of where each protection lives |
| 4 | **Build-path / identity scrub** — a **relative** source name is passed to `Extension(...)` instead of the absolute path | `build.py` | Stops `C:\Users\mohan\…\config.c` (developer username + project layout) being embedded in the `.pyd` |
| 5 | **Module-name obfuscation** — security modules renamed away from self-describing names | see rename table below | Removes obvious anchors (`secrets`, `anti_debug`, `request_signer`) that tell an analyst exactly what each `.pyd` does |
| 6 | **Stale-artifact purge before every build** — wipes leftover `.pyd`/`.c` from the source tree | `build.py` (`purge_stale_artifacts`) | An interrupted build leaving compiled modules in `source/` (which would import over the `.py` and misfire the anti-tamper guard during dev) |

**Module rename map** (self-describing → neutral):

| Old name | New name |
|---|---|
| `core/secrets.py` | `core/codec.py` |
| `security/anti_debug.py` | `security/envprobe.py` |
| `security/process_monitor.py` | `security/watchdog.py` |
| `security/system_locker.py` | `security/wsession.py` |
| `network/request_signer.py` | `network/netheaders.py` |
| `network/login_proxy.py` | `network/localgw.py` |

**Honest limits (from the assessment, not yet closed):** the highest-impact fix is
**architectural, not obfuscation** — the client-side shared HMAC secret should be
replaced with **per-session, server-issued tokens**, and enforcement decisions
(anti-debug, process kill, keyboard lock are all runtime-patchable) should be
backed by a server that treats the client as *deterrence, not proof*. Certificate
pinning and signed/checksummed updates remain open. Obfuscation raises the effort;
it does not change the outcome for a motivated analyst. See
[`RE_ASSESSMENT.md `](../RE_ASSESSMENT.md) for the full prioritized roadmap.

---

## 4. Build & Packaging

**Chosen:** Nuitka (+ optional Cython) → native distribution; Inno Setup → installer.

| Reason | Detail |
|---|---|
| Native compilation | Nuitka compiles Python → C → native binary: better performance and no shippable `.py` source |
| Hardening | `--cython` and `--harden` flags add obfuscation/optimization; docstrings stripped and build paths made relative (see 3.13) |
| Standard installer | Inno Setup produces `TPBrowser_Setup_x.x.x.exe`, matching the in-app updater format |
| Full runtime shipped | The entire `main.dist` folder ships — the exe can't run alone because Qt WebEngine carries the Chromium runtime |

**Build dependencies (`requirements-build.txt`):** `nuitka`, `Cython`, `PyQt6`,
`PyQt6-WebEngine`, `psutil`, `pywifi`, `cryptography`

---

## 5. Runtime Architecture

```
main.py (parent launcher)
  ├── integrity + anti-debug/VM checks
  ├── single-instance mutex
  ├── optional update check + update window
  ├── Task Manager lockdown
  └── creates SecureExamDesktop → launches child with --secure-mode
        ├── low-level keyboard hook (compiled build only)
        ├── process sentinel + periodic anti-debug loop
        ├── localhost reverse proxy
        └── PyQt6 UI (Qt WebEngine / Chromium)
              ├── college/portal selector
              ├── restricted full-screen browser tabs
              └── Wi-Fi dialog
```

**Layered layout:**

- `core/` — config, codec (secret obfuscation), logging
- `network/` — proxy (`localgw`), signer (`netheaders`), updater, wifi
- `security/` — anti-debug (`envprobe`), process monitor (`watchdog`), system locker (`wsession`)
- `ui/` — browser shell, engine policy, selectors, dialogs

---

## 6. Decision Summary

| Layer | Technology chosen | Primary reason |
|---|---|---|
| Language | Python 3.13 | Fast development + deep Win32 access + compilable |
| App framework / UI | PyQt6 (Qt 6) | Native desktop shell and bundled browser engine in one |
| Rendering engine | Chromium (Qt WebEngine) | Portal compatibility, WebRTC/camera, flag-level control |
| Request control | `QWebEngineUrlRequestInterceptor` | HMAC signing + navigation filtering |
| Process / security | `psutil` + `ctypes`/Win32 | Blocklist enforcement, hooks, mutex, registry |
| Wi-Fi | `pywifi` | In-desktop network management |
| Crypto | `cryptography` (Fernet) | Obfuscate embedded HMAC key |
| **RE resistance** | **Cython hardening + anti-tamper guards** | **Docstring/path scrub, bare-Python import guard, on-demand key, module renames (see 3.13)** |
| Compilation | Nuitka + Cython | Native binary, source removed, hardened |
| Installer / updates | Inno Setup | Standard Windows installer + in-app update path |

> **Bottom line on RE:** the obfuscation stops someone from `strings`-ing the
> secrets out in five seconds — real value against low-effort cheating — but it
> does not stop a motivated analyst with a debugger. The durable fix is
> architectural: don't ship a secret the client can be tricked into revealing.
> Harden 3.13 for hygiene; invest in per-session server tokens for actual security.
