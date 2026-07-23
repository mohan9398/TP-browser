# TeleBrowser — Documentation Index

TeleBrowser is a Windows-only secure examination browser built with Python,
PyQt6/Qt WebEngine, and direct Windows API calls. The current application starts
with a college/portal selector, launches the selected exam site in a restricted
full-screen browser, and provides security, networking, Wi-Fi, and update
features around that browser session.

## Read these documents

| Document | Purpose |
|---|---|
| `PROJECT_EXPLAINED.md` | Full plain-English walkthrough of the current application |
| `DEVELOPER_GUIDE.md` | Architecture and development orientation |
| `main.md` | Parent launcher, secure child, and startup lifecycle |
| `network.md` | Reverse proxy, HMAC signing, updates, and Wi-Fi |
| `security.md` | Keyboard lockdown, process monitoring, and anti-debug/VM checks |
| `ui.md` | College selector, browser window, browser engine, Wi-Fi, and update UI |
| `BUILD_GUIDE.md` | Nuitka/Cython build modes and output |
| `PRODUCTION_DEPLOYMENT.md` | Pre-release configuration and security checklist |

## Current application flow

```text
Parent launcher
  ├── integrity and environment checks
  ├── single-instance enforcement
  ├── compiled-build update check
  └── secure Windows desktop
        └── child process (--secure-mode)
              ├── keyboard/process/debug protections
              ├── localhost proxy
              └── PyQt6 UI
                    ├── college and portal selection (core/labs.json)
                    ├── restricted browser tabs
                    └── Wi-Fi management
```

## Source areas

- `main.py` — application lifecycle and parent/child orchestration.
- `core/` — configuration, portal data, HMAC-key obfuscation, and logging.
- `network/` — localhost proxy, signing, installer-based updates, and Wi-Fi.
- `security/` — Task Manager/keyboard lockdown, process sentinel, and
  debugger/VM detection.
- `ui/` — selector, browser shell, WebEngine policy, Wi-Fi dialog, and update
  progress window.
- `build.py` and `installer.iss` — standalone build and installer packaging.

## Important current facts

- The process sentinel scans approximately every 59 seconds.
- Clipboard clearing occurs once at startup, followed by a single delayed clear
  500 ms later; it is not a repeating 500 ms timer.
- Updates download and run a complete Inno Setup installer, not a replacement
  executable.
- File logging is disabled by default and enabled with
  `TELE_BROWSER_DEBUG=1`.
- Portal hosts from `core/labs.json` must also exist in `ALLOWED_DOMAINS`.
- Current infrastructure uses development IPs and plain HTTP and is not ready
  for broad production deployment without the deployment checklist.

The repository-root `README.md` contains the concise setup, build, configuration,
and production overview.
