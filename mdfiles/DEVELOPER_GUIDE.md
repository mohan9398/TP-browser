# Secure Exam Browser — Developer Guide

This document explains the purpose, architecture, and major code paths of the application. It is written for a new developer who wants to understand what this project does, how the Wi-Fi support works, and where the relevant code lives.

---

## 1. What this app does

This application is a Windows-only secure browser built for exam proctoring. Its main goal is to create a locked-down exam environment while still letting the student manage network connectivity and take proctored exams.

Primary capabilities:

- Launches a secure browser in an isolated Windows desktop
- Blocks escape keys and system shortcuts
- Kills forbidden applications during the exam
- Detects debuggers and virtual machines
- Uses a local HTTP proxy to rewrite exam-origin traffic
- Signs outgoing requests with HMAC headers
- Provides a Wi-Fi manager inside the app
- Offers a full-screen browser with limited navigation controls

---

## 2. High-level architecture

### 2.1 Two-process launcher model

The app runs in two modes:

- **Launcher mode** (parent process): performs security checks, enforces single instance, updates, and creates the secure desktop.
- **Secure mode** (child process): runs inside the isolated desktop, installs the keyboard hook and process sentinel, launches the browser UI, and starts the local proxy.

The mode is selected by the `--secure-mode` flag.

### 2.2 Main directories and responsibilities

```
TP-browser/
├── main.py                   # Launcher and secure-mode orchestration
├── core/                     # Shared configuration and logging
├── network/                  # Networking layer (proxy, signer, updater, Wi-Fi)
├── security/                 # System lockdown and anti-debug protection
└── ui/                       # Qt UI components
```

### 2.3 Core modules

- `main.py`
  - Checks integrity and anti-debug protections
  - Enforces single-instance execution
  - Runs auto-update before launching secure mode
  - Creates and switches to a separate Windows desktop
  - Starts the secure browser child process

- `core/config.py`
  - Stores app constants, allowed domains, update URL, and security settings
  - Includes Chromium flags used when launching the browser

- `network/login_proxy.py`
  - Provides a local HTTP proxy that rewrites exam traffic
  - Helps exam server work under Chromium security restrictions

- `network/request_signer.py`
  - Injects HMAC headers into outgoing requests from the browser
  - Ensures tamper-proof request authentication

- `network/updater.py`
  - Checks a remote endpoint for newer versions
  - Downloads and swaps the executable if an update is found

- `network/wifi_manager.py`
  - Scans Wi-Fi networks and connects to selected SSIDs
  - Uses `pywifi` and Windows `netsh` when needed

- `ui/main_window.py`
  - Builds the browser window and toolbar
  - Provides the Network button and offline overlay
  - Creates tabs with `QWebEngineView`

- `ui/dialogs.py`
  - Implements the `WifiDialog` used by the browser UI
  - Drives Wi-Fi scanning and connection flows

- `security/system_locker.py`
  - Installs the keyboard hook
  - Disables Task Manager

- `security/process_monitor.py`
  - Kills forbidden processes repeatedly

- `security/anti_debug.py`
  - Detects debuggers, virtualization, and other suspicious environments

---

## 3. Wi-Fi support: what it does and why

### 3.1 Why Wi-Fi support exists

This secure browser is used in exam environments where the student may need to connect to a network while remaining inside the locked exam interface. The built-in Wi-Fi manager allows the user to:

- scan for available networks
- reconnect to networks the OS already knows
- enter a password for new networks
- recover from connection loss without leaving the secure environment

Without this feature, students would have to exit the secure browser or use Windows settings, which would break the lockdown model.

### 3.2 Where the Wi-Fi code lives

The main Wi-Fi implementation is in:

- `network/wifi_manager.py`
- `ui/dialogs.py`
- `ui/main_window.py`

### 3.3 How the Wi-Fi flow works

1. The user clicks the **Network** button in the browser toolbar.
2. `SecureBrowser.open_wifi()` loads `WifiDialog`.
3. `WifiDialog` creates a `WiFiManager` instance.
4. `WiFiManager.scan_async()` starts a background scan thread.
5. Scan results are emitted to the dialog via the `scan_complete` Qt signal.
6. The dialog shows available SSIDs and marks saved networks.
7. When the user clicks **Connect**, the dialog calls `WiFiManager.connect_async()`.
8. The connection worker performs the actual `pywifi` connect sequence.
9. If the connection succeeds, the dialog closes and the browser reloads the current page.

### 3.4 Detailed code behavior

#### `network/wifi_manager.py`

- `WiFiManager.__init__()`
  - Creates a `QObject` with two signals: `scan_complete` and `connect_complete`
  - Calls `_init_interface()` to select the first Wi-Fi adapter found by `pywifi`

- `_init_interface()`
  - Uses `pywifi.PyWiFi().interfaces()` to locate the adapter
  - Keeps the first interface in `self._interface`
  - Logs a warning if no adapter is found

- `get_saved_ssids()`
  - Returns SSIDs from saved network profiles on the PC
  - Enables one-click reconnect for known networks

- `get_saved_password(ssid)`
  - Windows-only method using `netsh wlan show profile name=<ssid> key=clear`
  - Returns the saved password if the app is running elevated
  - Allows the dialog to reveal stored credentials for debugging or support

- `scan_async()`
  - Clears the cancellation flag
  - Starts `_scan_worker()` in a daemon thread

- `_scan_worker()`
  - Calls `self._interface.scan()`
  - Waits up to ~3 seconds in 0.1s slices so cancellation can interrupt quickly
  - Reads `scan_results()` and emits a sorted list of unique SSIDs
  - Emits error messages such as `No Wi-Fi Adapter`, `Scan Failed`, or `No Networks Found`

- `connect_async(ssid, password)`
  - Starts `_connect_worker()` in a daemon thread

- `_connect_worker(ssid, password)`
  - Disconnects any current Wi-Fi connection first
  - Looks for an existing profile matching the selected SSID
  - If no profile exists, creates a new `pywifi.Profile()`
    - Open network: `AUTH_ALG_OPEN` and `CIPHER_TYPE_NONE`
    - Password network: `AKM_TYPE_WPA2PSK`, `CIPHER_TYPE_CCMP`, and stores `profile.key`
  - Connects using `self._interface.connect(profile)`
  - Waits up to 15 seconds for `IFACE_CONNECTED`, then emits success or timeout

#### `ui/dialogs.py`

- `WifiDialog` is the user interface for Wi-Fi management.
- It preserves the clean SSID in each list item using a Qt item role (`SSID_ROLE`).
- `refresh()` starts a scan and disables the refresh button until results arrive.
- `on_scan_complete(ssids)` updates the list and status label.
- `connect()` determines whether the network is saved:
  - Saved network: connect immediately without prompting for a password
  - New network: prompt the user for the password
- `show_password()` tries to reveal the stored password for a selected saved network.
- `closeEvent()` cancels any in-progress scan so background threads do not keep running.
- `on_connect_complete(success, message)` shows a success or failure message and closes the dialog on success.

#### `ui/main_window.py`

- `create_toolbar()` adds the **Network** button to the browser toolbar.
- `open_wifi()` imports `WifiDialog` lazily and executes it as a modal dialog.
- When `WifiDialog` returns `QDialog.DialogCode.Accepted`, the browser reloads the current page.
- The offline overlay text explicitly tells the user the issue is usually a Wi-Fi or network problem.

### 3.5 Why this design was chosen

- The Wi-Fi scan and connect logic runs in background threads so the UI stays responsive.
- Qt signals allow the network layer to communicate with the UI without blocking.
- Saved SSIDs are detected so the user does not have to re-enter known passwords.
- The Wi-Fi tool is embedded in the secure browser so the student does not leave the locked environment.

---

## 4. Other important features

### 4.1 Local HTTP proxy and exam origin handling

- `network/login_proxy.py` launches a local proxy server before Qt initializes.
- The browser is configured to send exam traffic through the proxy.
- The proxy rewrites request URLs, strips CORS headers, and handles cookies.
- This makes an HTTP-based exam server behave like a secure origin for Chromium.

### 4.2 HMAC request signing

- `network/request_signer.py` injects headers on every request using the `QWebEngineUrlRequestInterceptor` API.
- Headers include `X-Exam-Time`, `X-Exam-Nonce`, and `X-Exam-Signature`.
- The exam backend can verify requests came from the genuine browser and have not been tampered with.

### 4.3 Auto-update

- `network/updater.py` checks `UPDATE_CHECK_URL` for the latest version.
- If an update exists, it downloads the new executable and creates a swap script.
- The launcher process can update itself before entering the secure exam desktop.

### 4.4 Security lockdown

- `security/system_locker.py` installs a low-level keyboard hook and disables Task Manager.
- `security/process_monitor.py` periodically scans running processes and kills forbidden ones.
- `security/anti_debug.py` detects debuggers and virtual machines and prevents the app from running if suspicious activity is found.

---

## 5. Key configuration points

### `core/config.py`

- `APP_VERSION`: version string shown in the UI and used for update checks.
- `UPDATE_CHECK_URL`: endpoint used by the auto-updater.
- `START_URL`: the initial exam URL loaded into the browser.
- `ALLOWED_DOMAINS`: trusted domains the browser treats as exam-related.
- `QT_FLAGS`: Chromium command-line flags needed for the browser to function in this secure environment.
- `FORBIDDEN_APPS` / `SCREENSHOT_TOOLS`: the list of apps the process sentinel should kill.

### `core/secrets.py`

- Holds the encrypted HMAC secret key used by `request_signer.py`.
- If this file is missing or decrypted data fails, the app falls back to a default placeholder key.

---

## 6. How to start working on this project

1. Install the required Python dependencies:

```bash
pip install PyQt6 PyQt6-WebEngine psutil pywifi cryptography
```

2. Run the app in development mode:

```bash
python main.py
```

3. Use the Network button to test Wi-Fi scanning and connection.
4. Inspect `main.py` first to understand launcher vs secure mode.
5. Follow the Qt signal flow between `ui/dialogs.py` and `network/wifi_manager.py` for Wi-Fi behavior.

---

## 7. Notes for new developers

- The app is Windows-only. Many features rely on Windows-specific APIs and tools.
- The Wi-Fi flow is not a standalone network manager; it is intentionally minimal and designed to work inside the locked browser.
- The compiled build behavior may differ from pure Python execution, especially around keyboard hooks, desktop isolation, and Task Manager disabling.
- When editing Chromium flags, remember they are set before any PyQt6 import to ensure Chromium sees them.

---

## 8. Recommended next improvements

- Add stronger error reporting and logging for Wi-Fi connection failures.
- Improve Wi-Fi password handling and validation for WPA3 or enterprise networks.
- Expose `WifiDialog` results more explicitly so `SecureBrowser` can react to connection state changes.
- Harden the update flow with HTTPS and signature verification.
- Add unit tests for `WiFiManager` and the dialog flow.
