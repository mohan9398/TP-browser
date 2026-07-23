# Production Deployment Checklist

Everything below is currently pointed at development/test infrastructure
(local IPs like `172.168.15.x`, `172.168.13.69`). Before shipping a build to
real students, go through this list top to bottom.

## 1. `core/config.py`

| Setting | Current (dev) value | What to do for production |
|---|---|---|
| `UPDATE_CHECK_URL` (line ~29) | `http://172.168.13.69:9999/download` | Point at the real, stable update server. This must be reachable from every exam machine, on whatever network they're deployed on — not just your dev LAN. Consider HTTPS (see §5). |
| `TARGET_ORIGIN` (line ~31) | `http://172.168.15.213` | The real exam portal server's origin. `network/login_proxy.py` proxies all traffic through this — get it wrong and the exam portal won't load at all. |
| `TARGET_NETLOC` (line ~32) | `172.168.15.213` | Must be the host[:port] part of `TARGET_ORIGIN`, kept in sync manually (nothing derives one from the other). |
| `ALLOWED_DOMAINS` (line ~34) | List of dev/test IPs (`192.168.2.5`, `172.168.15.213`, `172.168.15.216`, `172.168.15.218`, `172.168.13.69`, `ksjc.teleuniv.in`, `teleuniv.in`) | Trim to exactly the domains/IPs the production exam portal, test center, and update server actually use. Anything left in this list that isn't real infra is dead weight; anything missing will get blocked by the browser's own domain restriction. |
| `APP_SECRET_KEY` / `_APP_SECRET_KEY_ENC` (line ~17) | Encrypted dev key, with a **plaintext fallback** `"my_production_secret_key_12345"` if decryption fails | Rotate this for production: `python -c "from core.secrets import encrypt; print(encrypt('NEWKEY'))"`, paste the output into `_APP_SECRET_KEY_ENC`. Also seriously consider removing (or at least hardening) the plaintext fallback — if `secure_browser.core.secrets` ever fails to import in a production build, the app silently falls back to a hardcoded, publicly-visible-in-source-control key instead of refusing to start. |
| `APP_VERSION` (line ~5) | `"1.0.0"` | Bump for every release — this is what the auto-updater compares against the server's manifest to decide whether to update. |

## 2. `core/labs.json`

All portal URLs per college (`NGIT`, `KMIT`, `KMEC`, `KMCE`) currently point
at dev IPs (`172.168.15.216:8000` for Test Center, `172.168.15.213/toofan`
for Toofan). Replace with real production URLs per college before shipping.

This file sits **next to the installed exe** (`installer.iss` copies it from
`core\labs.json` to `{app}\labs.json`) specifically so it can be hand-edited
post-install without rebuilding — but the copy that ships in the installer
should already have correct production URLs as the default, not dev ones.

## 3. `installer.iss`

- `AppId` (`{{A3F2D1C4-8B7E-4F6A-9C2D-1E5B3A7F8D90}`) — **never change this
  once the first production version ships.** The whole silent-auto-update
  strategy relies on Inno Setup recognizing a new installer as an in-place
  upgrade of the same app, which only works if `AppId` stays identical across
  every version forever.
- `AppVersion` / `VersionInfoVersion` — bump to match `core/config.py`'s
  `APP_VERSION` for every release.
- `AppPublisherURL` (`https://teleuniv.in`) — update if the publisher domain
  changes.
- The installer is currently **unsigned**. Windows SmartScreen / antivirus
  may flag or block an unsigned installer, especially one that a background
  updater downloads and silently executes. Consider code-signing before
  wide deployment.

## 4. Auto-update mechanism

`network/updater.py` downloads the new **Inno Setup installer** (not a raw
exe) and runs it silently (`/SILENT /SUPPRESSMSGBOXES /NORESTART`),
relying on `installer.iss`'s fixed `AppId` so Inno Setup treats it as an
in-place upgrade of everything under `{app}` — this correctly updates
Cython-compiled `.pyd` files from a `--cython` build too (a single-exe
swap would have missed those; see `build.py`'s `CYTHON_MODULES`).

Flow (`main.py:_check_for_updates_blocking`, `ui/update_progress.py`):
launcher checks the server on startup (parent process only, never inside
the secure exam desktop) → if newer, a small window opens and
**downloads automatically** → once downloaded, a
*"Update ready — click to install"* button appears → student clicks it →
installer runs silently → launcher relaunches itself. If there's no
update, the check fails, or the download fails, the window never appears
(or closes itself) and the exam launches normally — nothing blocks the
student in those cases.

This does **not** verify a checksum on the downloaded installer — that was
an explicit decision, but understand the tradeoff: anyone who can intercept
or spoof traffic to `UPDATE_CHECK_URL` can get an arbitrary installer
executed with admin rights on every machine that checks in. Revisit before
wide rollout if the update server isn't on a fully trusted, isolated network.

Also confirm: does the exam machine deployment run the browser elevated, or
will the silent install trigger a UAC prompt with nobody present to click
it? That's the one part of this flow that isn't fully unattended — Windows'
own elevation prompt can't be suppressed by Inno Setup's silent flags.

The update flow does not do its own logging (removed after initial
verification — it worked end-to-end, confirmed via a temporary dedicated
log file, then the logging was stripped back out). If it needs to be
diagnosed again on a student machine, either temporarily reinstate a log
file in `network/updater.py`/`ui/update_progress.py`, or run with
`TELE_BROWSER_DEBUG=1` and add log calls that go through `core/logger.py`.

## 5. HTTP vs HTTPS

Everything is currently plain HTTP: `UPDATE_CHECK_URL`, `TARGET_ORIGIN`,
and every portal URL in `labs.json`. There's already a
`# TODO: Change to HTTPS when available` above `UPDATE_CHECK_URL` in
`config.py`. Plain HTTP means anything on the same network path can read or
tamper with exam traffic and update payloads. Move to HTTPS before this
goes anywhere outside a fully trusted, isolated exam LAN — especially for
the update channel, given §4's checksum tradeoff.

## 6. Build command for production

```
python build.py --cython --harden
```
per `build.py`'s own "BEST PROTECTION" recommendation — then package the
resulting `build/main.dist/` through `installer.iss` in Inno Setup. Do not
ship the raw `main.dist` folder or the un-installed dev build to students.

## Quick pre-ship grep

To catch anything missed above, search the repo for leftover dev
infrastructure before cutting a release:

```powershell
rg -n "172\.168\.|192\.168\.2\.5" core network ui -g "*.py" -g "*.json"
```
Anything that shows up here and isn't real production infrastructure needs
to be fixed before shipping.
