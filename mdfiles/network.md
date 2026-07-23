# `network/` — Networking Layer

This folder contains everything the browser does that involves **talking over the
network**: routing exam traffic through a local proxy, signing outgoing requests
so the exam server can trust them, checking for and applying software updates, and
letting the student connect to Wi-Fi without leaving the locked-down browser.

## Files at a glance

| File | Responsibility |
|------|----------------|
| `login_proxy.py` | A local HTTP proxy that sits between the browser and the exam server, rewriting URLs/cookies so an HTTP exam site behaves like a "secure" same-origin site. |
| `request_signer.py` | Adds tamper-proof HMAC signature headers to outgoing requests so the exam server can verify they came from the real browser. |
| `updater.py` | Checks the update manifest, downloads an Inno Setup installer, and launches a silent in-place upgrade. |
| `wifi_manager.py` | Scans for and connects to Wi-Fi networks from inside the browser. |

---

## `login_proxy.py` — the local reverse proxy

The exam portal is served over plain **HTTP** (see `TARGET_ORIGIN` in the
config). Modern Chromium disables sensitive features (camera, microphone,
secure cookies) on insecure HTTP origins. To work around this, the browser does
**not** talk to the exam server directly. Instead:

```
Browser  ──►  Local Proxy (http://127.0.0.1:<random port>)  ──►  Exam Server (http://172.168.15.213)
         ◄──                                                ◄──
```

The proxy is treated as a trusted local origin, which unlocks the media APIs the
proctoring system needs.

**What it actually does:**

- **`start_proxy()`** — binds an HTTP server to `127.0.0.1` on a *random free
  port* (port `0` lets the OS pick), runs it in a daemon thread, and returns the
  chosen port. `get_proxy_origin()` / `get_proxy_port()` expose the result to the
  rest of the app.
- **`ProxyHandler`** — handles every request method (`GET`, `POST`, `PUT`,
  `DELETE`, `OPTIONS`). For each request it:
  1. Rebuilds the real target URL (`_build_target_url`).
  2. Forwards the request to the exam server, fixing up the `Host`, `Origin`,
     and `Referer` headers so the server sees its own address, and asking for an
     uncompressed (`identity`) response.
  3. Reads the response back.
- **URL rewriting** (`rewrite_text_payload`) — in textual responses (HTML, JS,
  CSS, JSON) it replaces every reference to the real server address with the
  proxy address. It handles the many forms a URL can take: plain, backslash-
  escaped (`\/` in JSON/JS), scheme-relative (`//host`), and HTML-entity escaped.
  This keeps the browser "inside" the proxy origin as the student navigates.
- **Redirect rewriting** (`rewrite_location`) — rewrites `Location` headers on
  3xx redirects so they point back through the proxy. A custom
  `NoRedirectHandler` stops Python from silently following redirects itself, so
  the browser stays in control.
- **Cookie rewriting** (`rewrite_set_cookie`) — strips the `Domain=` attribute
  (making cookies host-only for `127.0.0.1`) and removes the `Secure` flag so
  cookies are not dropped over local HTTP.
- **Text vs. binary handling** — textual content is fully buffered so it can be
  decoded, rewritten, and re-encoded. Binary content (images, video) is
  **streamed** in 8 KB chunks for performance, with no buffering.
- **Compression** (`_decompress`) — transparently decompresses `gzip`, `deflate`,
  and `br` (Brotli, if available) before rewriting.
- **Threaded server** (`ThreadedProxy`) — each request is served on its own
  thread so many resources can load in parallel.
- Adds permissive `Access-Control-Allow-Origin: *` headers to avoid CORS issues.

---

## `request_signer.py` — HMAC request signing

`HmacRequestInterceptor` is a Qt `QWebEngineUrlRequestInterceptor` that runs on
**every** request the browser makes. For each non-static request it attaches three
headers:

- `X-Exam-Time` — current Unix timestamp.
- `X-Exam-Nonce` — 8 random bytes (hex) to make every request unique.
- `X-Exam-Signature` — `HMAC-SHA256(secret_key, "timestamp:nonce")`.

The exam server shares the same secret key (`APP_SECRET_KEY` from the config) and
can recompute the signature to confirm the request genuinely came from this
browser and was not forged or replayed.

**Performance note:** static/background requests (`.css`, `.js`, images, `theme`,
`pluginfile`, `webservice`) are skipped via a fast `_SKIP_TOKENS` check so signing
only happens where it matters.

---

## `updater.py` — installer-based auto-update

The current updater replaces the complete installed application through Inno
Setup; it does not swap one executable. This matters because the standalone
distribution contains Qt/WebEngine files and may contain Cython-compiled `.pyd`
modules that must be upgraded together.

- **`check_for_update()`** — only contacts the server for a compiled build. It
  returns a status tuple rather than directly changing the installation. The
  manifest must contain a newer `version` and an installer `url`.
- **`_version_tuple()`** — converts a dotted version string into integers for a
  numeric comparison with `APP_VERSION`.
- **`download_installer()`** — downloads the installer in 1 MB chunks to a new
  `tpbrowser_update_*` temporary directory.
- **`launch_silent_install_and_relaunch()`** — writes `run_update.bat`, waits for
  the launcher to exit, runs the installer with
  `/SILENT /SUPPRESSMSGBOXES /NORESTART`, relaunches the browser, and removes the
  batch file.
- **`AutoUpdater`** — remains only as a backwards-compatible wrapper around the
  function-based API.

`main.py` performs the check in the parent launcher. When an update is
available, `ui/update_progress.py` starts the download on a `QThread`, shows an
indeterminate progress window, and reveals an install button after the download
finishes. A failed check or download does not block normal exam startup.

> The application does not verify a checksum or signature for a downloaded
> installer. The manifest URL and download URL are currently trusted as-is.

---

## `wifi_manager.py` — Wi-Fi control

`WiFiManager` (a Qt `QObject`) lets the student manage Wi-Fi without breaking out
of the locked browser. It uses the `pywifi` library and emits Qt signals so the
UI stays responsive:

- **`scan_async()` / `_scan_worker()`** — scans for networks on a background
  thread and emits `scan_complete` with a sorted, de-duplicated list of SSIDs.
- **`connect_async()` / `_connect_worker()`** — connects to a chosen SSID on a
  background thread: disconnects current, reuses an existing profile or builds a
  new WPA2-PSK (or open) profile, connects, and polls for up to ~15 seconds for a
  successful connection before emitting `connect_complete(success, message)`.

All work happens off the UI thread, and results are delivered via signals so the
`WifiDialog` in the UI layer can update safely.

---

## How the network layer ties together

- `main.py` starts the **proxy** before Qt loads and passes its origin to the UI.
- The **UI** loads the start URL *through* the proxy origin.
- The **request signer** stamps every request the browser sends.
- The **updater** runs once at launch (compiled parent process only); update
  downloads are presented through `UpdateProgressWindow`.
- The **Wi-Fi manager** is opened on demand from the toolbar's Network button.
