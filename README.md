# TeleBrowser — Secure Exam Browser

TeleBrowser is a Windows-only, locked-down browser for online examinations. It
uses PyQt6 and Qt WebEngine for the browser UI, Windows APIs for desktop and
keyboard isolation, and a local reverse proxy for HTTP-based exam portals that
need camera and microphone access.

## Current features

- **Two-process secure launch** — a parent launcher performs preflight checks,
  creates `SecureExamDesktop`, and starts a child process there with
  `--secure-mode`.
- **College and portal selection** — the initial screen is populated from
  `core/labs.json`; the chosen portal is then opened in the browser.
- **Desktop and keyboard lockdown** — disables Task Manager and blocks Windows
  keys, Alt+Tab, Alt+Esc, Alt+F4, Alt+Space, and Ctrl+Shift+Esc.
- **Process sentinel** — scans approximately every 59 seconds and terminates
  configured browsers, communication tools, remote-access clients, and screen
  capture applications.
- **Anti-debug and anti-VM checks** — checks processes, the Windows debugger API,
  and VM-related registry values at startup and periodically during an exam.
- **Local HTTP proxy** — binds to a random localhost port, forwards requests to
  `TARGET_ORIGIN`, rewrites text payloads, redirects, and cookies, and streams
  binary responses.
- **HMAC request signing** — adds `X-Exam-Time`, `X-Exam-Nonce`, and
  `X-Exam-Signature` headers to non-static browser requests.
- **Camera and microphone support** — configures Chromium and Qt WebEngine to
  grant media permissions needed by approved exam origins.
- **Built-in Wi-Fi management** — scans, reconnects to saved networks, and
  connects to new WPA2/open networks without leaving the secure desktop.
- **Installer-based updates** — compiled builds check a JSON manifest, download
  an Inno Setup installer in the background, and install it after the user
  clicks the update button.
- **Single-instance enforcement** — a named Windows mutex prevents duplicate
  launchers.

## Runtime architecture

```text
main.py (parent launcher)
  ├── integrity and anti-debug/VM checks
  ├── single-instance mutex
  ├── optional update check and update window
  ├── Task Manager lockdown
  └── creates SecureExamDesktop and launches --secure-mode
        ├── low-level keyboard hook (compiled build)
        ├── process sentinel and periodic anti-debug loop
        ├── localhost reverse proxy
        └── PyQt6 UI
              ├── college/portal selector
              ├── restricted browser tabs
              └── Wi-Fi dialog
```

## Repository layout

```text
TP-browser/
├── main.py                    # Parent/child orchestration
├── build.py                   # Nuitka/Cython build driver
├── installer.iss              # Inno Setup installer definition
├── requirements-build.txt     # Runtime and build dependencies
├── core/
│   ├── config.py              # URLs, allowlists, blocklists, Chromium flags
│   ├── labs.json              # Colleges, portals, and portal URLs
│   ├── secrets.py             # Embedded-key obfuscation helpers
│   └── logger.py              # Opt-in rotating debug logger
├── network/
│   ├── login_proxy.py         # Local reverse proxy
│   ├── request_signer.py      # HMAC request interceptor
│   ├── updater.py             # Update check, download, and silent install
│   └── wifi_manager.py        # Asynchronous Wi-Fi operations
├── security/
│   ├── anti_debug.py          # Debugger and VM detection
│   ├── process_monitor.py     # Forbidden-process sentinel
│   └── system_locker.py       # Keyboard hook and Task Manager policy
├── ui/
│   ├── main_window.py         # Full-screen browser shell
│   ├── browser_engine.py      # Navigation and media-permission policy
│   ├── college_selector.py    # College/portal selection UI
│   ├── dialogs.py             # Wi-Fi dialog
│   └── update_progress.py     # Update download/install window
└── mdfiles/                   # Detailed project documentation
```

Source imports use the package name `secure_browser`. During builds,
`build.py` creates a temporary directory junction with that name when the
checkout directory itself has a different name.

## Configuration

The main settings are in `core/config.py`; portal entries are in
`core/labs.json`.

| Setting | Current value/purpose |
|---|---|
| `APP_VERSION` | `1.0.0`; used by the UI, build metadata, and updater |
| `UPDATE_CHECK_URL` | Development update-manifest endpoint |
| `TARGET_ORIGIN` / `TARGET_NETLOC` | Face-login server reached through the local proxy |
| `ALLOWED_DOMAINS` | Exact hosts and subdomains allowed by `SecurePage` |
| `APP_SECRET_KEY` | Decrypted embedded HMAC key with a plaintext fallback |
| `FORBIDDEN_APPS` / `SCREENSHOT_TOOLS` | Processes terminated by the sentinel |
| `QT_FLAGS` | Chromium media, security, and WebRTC flags |

Every host used in `core/labs.json` must also be permitted by
`ALLOWED_DOMAINS`. The current Google portal entry does not satisfy that rule
because `google.com` is not currently in the allowlist.

## Development

Install the dependencies:

```powershell
pip install -r requirements-build.txt
```

The application is Windows-specific. Source-mode behavior is intentionally
safer than a compiled build: the low-level keyboard hook is only installed when
`sys.frozen` is true. Imports also require the project to be available as the
`secure_browser` package; the production build script creates that package-name
bridge automatically.

Enable diagnostic logging when needed:

```powershell
$env:TELE_BROWSER_DEBUG = "1"
python main.py
```

Logs are written to `%TEMP%\SecureExamBrowser\secure_browser.log` with five
rotating files of approximately 1 MB each. Logging is a no-op by default.

## Build and install

Recommended production build:

```powershell
python build.py --cython --harden
```

The output is `build/main.dist/SecureBrowser.exe` plus its supporting files.
Compile `installer.iss` with Inno Setup to produce
`installer/TPBrowser_Setup_1.0.0.exe`. The entire `main.dist` folder is required;
the executable cannot be distributed by itself.

## Production warnings

- Development IP addresses and portal URLs are still present in
  `core/config.py` and `core/labs.json`.
- The exam, portal, and update endpoints currently use plain HTTP.
- Downloaded update installers are not checksum- or signature-verified by the
  application.
- `certificateError()` currently accepts all certificate errors; certificate
  pinning or a trusted CA policy is not implemented.
- The embedded HMAC key is obfuscated, not securely provisioned, and a plaintext
  fallback remains in `core/config.py`.
- Silent installation still requires whatever Windows elevation policy applies
  on the exam machine.

See `mdfiles/PRODUCTION_DEPLOYMENT.md` before preparing a student release.
