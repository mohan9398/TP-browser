# TeleBrowser — Secure Exam Browser

A Windows-based secure browser for online examination proctoring. Locks down the system environment during exams to prevent cheating via process monitoring, keyboard blocking, desktop isolation, and anti-debug/anti-VM detection.

---

## Features

- **Desktop Isolation** — Creates a dedicated Windows desktop (`SecureExamDesktop`) so only the browser is accessible during the exam
- **Keyboard Lockdown** — Low-level WH_KEYBOARD_LL hook blocks Alt+Tab, Win key, Alt+F4, Ctrl+Shift+Esc, and similar escape shortcuts
- **Process Sentinel** — Background thread kills forbidden applications (browsers, screen capture tools, remote desktop clients, messaging apps) every 2 seconds
- **Anti-Debug / Anti-VM** — Detects debuggers (gdb, x64dbg, radare2, etc.) and virtual machines (VMware, VirtualBox, Hyper-V, KVM) via process inspection, registry keys, and the `IsDebuggerPresent` WinAPI
- **Local HTTP Proxy** — Runs on a dynamic localhost port; rewrites origin URLs in HTML/JS/JSON payloads, strips CORS headers, and manages cookies to allow the exam server to function under Chromium's security model
- **HMAC Request Signing** — Injects `X-Exam-Time`, `X-Exam-Nonce`, and `X-Exam-Signature` headers on every request using HMAC-SHA256
- **Camera / Microphone Proctoring** — Grants media permissions aggressively; injects a JS monitor for `getUserMedia` calls; allows WebRTC LAN ICE candidates
- **Clipboard Clearing** — Wipes the clipboard every 500 ms to prevent data exfiltration
- **Auto-Update** — Checks a remote update server on launch and swaps the executable via a batch script if a newer version is available
- **Single Instance Enforcement** — Uses a named global mutex to prevent running multiple instances
- **Domain Whitelist** — Navigation is restricted to approved exam server IPs and domains; all other requests are blocked

---

## Architecture

The application follows a **two-stage launcher** model:

```
main.py (Parent Process)
  ├── Anti-debug probe
  ├── Single-instance mutex check
  ├── Integrity checks (DLL presence, not running from Temp)
  ├── Auto-update check
  └── Spawns Child Process on SecureExamDesktop
        ├── Keyboard hook (WH_KEYBOARD_LL)
        ├── Process sentinel thread
        └── PyQt6 GUI (SecureBrowser + SecurePage + local proxy)
```

### Directory Layout

```
TP-browser/
├── main.py                   # Entry point; parent/child orchestration
├── core/
│   ├── config.py             # App constants, allowed domains, forbidden apps, secrets
│   └── logger.py             # Thread-safe logging singleton
├── network/
│   ├── login_proxy.py        # Local HTTP proxy with origin rewriting
│   ├── request_signer.py     # QWebEngineUrlRequestInterceptor — HMAC header injection
│   ├── updater.py            # Version check and executable swap
│   └── wifi_manager.py       # WiFi scan/connect via pywifi
├── security/
│   ├── system_locker.py      # Low-level keyboard hook + task manager disable
│   ├── process_monitor.py    # Sentinel thread that kills forbidden processes
│   └── anti_debug.py         # Debugger and VM detection
└── ui/
    ├── main_window.py        # SecureBrowser QMainWindow (tabs, nav, full-screen)
    ├── browser_engine.py     # SecurePage QWebEnginePage (permissions, domain filter, JS injection)
    └── dialogs.py            # WifiDialog
```

---

## Dependencies

| Library | Purpose |
|---------|---------|
| PyQt6 | GUI, WebEngine, URL interceptor |
| psutil | Process enumeration and termination |
| pywifi | WiFi scanning and connection |
| ctypes | Windows API calls (hooks, desktops, mutex) |

> No `requirements.txt` is currently present. Install dependencies manually:
> ```
> pip install PyQt6 PyQt6-WebEngine psutil pywifi
> ```

This application is **Windows-only** — it relies on WinAPI, winreg, and Windows-specific Chromium flags.

---

## Configuration

All tuneable values live in [core/config.py](core/config.py):

| Setting | Default | Description |
|---------|---------|-------------|
| `APP_VERSION` | `1.0.0` | Current build version |
| `EXAM_SERVER_URL` | `http://172.168.15.213/toofan` | Primary exam server |
| `UPDATE_CHECK_URL` | `http://172.168.15.218:3000/` | Auto-update endpoint |
| `USER_AGENT` | `TeleBrowser/1.0` | Chromium user-agent string |
| `SECRET_KEY` | `my_production_secret_key_12345` | HMAC signing secret — **change before production** |
| `ALLOWED_ORIGINS` | See config | Whitelist of IPs and domains |
| `FORBIDDEN_APPS` | See config | Process names to kill |

---

## Security Notes

- **HMAC secret** (`SECRET_KEY` in config.py) is currently a placeholder. Replace it with a strong random value before deployment.
- Certificate pinning is not yet implemented — the browser currently accepts all self-signed certificates.
- The anti-VM MAC address check is disabled by default due to false positives on some hardware.
- The logger (`core/logger.py`) is a stub and does not persist logs to disk.

---

## Running

> Intended to be compiled with Nuitka into a standalone Windows executable. Some security features (keyboard hook, desktop isolation) are gated behind `sys.frozen` and will not activate in a plain Python run.

```bash
python main.py
```

For a compiled build, distribute the output executable alongside any required DLLs (python3*.dll must be present in the same directory).

---

## Allowed Domains

Navigation is restricted to:

- `172.168.15.213` — Primary exam server
- `172.168.15.218` — Update/media server
- `172.168.15.215`, `172.168.15.216` — Supporting servers
- `ksjc.teleuniv.in`, `teleuniv.in` — Public exam portal
- `google.com` — Allowed for OAuth/login flows
- `192.168.2.5` — Local network resource
- `localhost` / `127.0.0.1` — Always allowed (local proxy)
## change above ip's according to your requirement.
