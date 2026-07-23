# -*- coding: utf-8 -*-
"""
Update flow: check_for_update() -> download_installer() -> (UI: user clicks
"install") -> launch_silent_install_and_relaunch().

Downloads the new Inno Setup installer (not a raw exe) and runs it
silently. Because installer.iss keeps a fixed AppId, Inno Setup treats this
as an in-place upgrade of everything under {app} -- including any
Cython-compiled .pyd files from a --cython build, which a single-exe swap
would have missed.

NOTE: checksum verification is intentionally not implemented -- the
manifest's "url" is trusted as-is. Anyone able to intercept/spoof traffic
to UPDATE_CHECK_URL can get an arbitrary installer executed with admin
rights on every machine that checks in. Revisit before wide rollout if
the update server isn't on a fully trusted, isolated network.
"""
import sys
import os
import json
import tempfile
import subprocess
import urllib.request

from secure_browser.core.config import APP_VERSION, UPDATE_CHECK_URL

CHECK_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 300

# check_for_update() status values
NOT_FROZEN = "not_frozen"
NO_UPDATE = "no_update"
UPDATE_AVAILABLE = "update_available"
CHECK_FAILED = "check_failed"


def _version_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


def _is_frozen() -> bool:
    executable = sys.executable.lower()
    argv0 = sys.argv[0].lower()
    return (
        getattr(sys, "frozen", False)
        or executable.endswith("main.exe")
        or executable.endswith("securebrowser.exe")
        or argv0.endswith("main.exe")
        or argv0.endswith("securebrowser.exe")
    )


def check_for_update():
    """
    Returns (status, remote_version, download_url).
    status is one of NOT_FROZEN / NO_UPDATE / UPDATE_AVAILABLE / CHECK_FAILED.
    remote_version/download_url are only set when status == UPDATE_AVAILABLE.
    """
    if not _is_frozen():
        return NOT_FROZEN, None, None

    try:
        headers = {"User-Agent": "SecureExamBrowser-Updater"}
        req = urllib.request.Request(UPDATE_CHECK_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            raw = resp.read()
    except Exception:
        return CHECK_FAILED, None, None

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return CHECK_FAILED, None, None

    latest_version = str(payload.get("version", "")).strip()
    download_url = str(payload.get("url", "")).strip()

    if not latest_version or not download_url:
        return CHECK_FAILED, None, None

    if _version_tuple(latest_version) <= _version_tuple(APP_VERSION):
        return NO_UPDATE, None, None

    return UPDATE_AVAILABLE, latest_version, download_url


def download_installer(url: str):
    """Downloads the installer to a temp file. Returns the local path, or None on failure."""
    tmp_dir = tempfile.mkdtemp(prefix="tpbrowser_update_")
    installer_path = os.path.join(tmp_dir, "installer.exe")
    try:
        headers = {"User-Agent": "SecureExamBrowser-Updater"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp, open(installer_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        return installer_path
    except Exception:
        return None


def launch_silent_install_and_relaunch(installer_path: str):
    """
    Runs the installer silently via a detached batch script (so the
    installer isn't trying to close its own parent process), then
    relaunches the app launcher and terminates the current process
    immediately. Does not return.
    """
    if _is_frozen():
        current_exe = os.path.abspath(sys.argv[0])
        relaunch_cmd = f'"{current_exe}"'
    else:
        # Dev-mode fallback; in practice launch_silent_install_and_relaunch
        # is only reached when _is_frozen() is True (see check_for_update).
        relaunch_cmd = f'"{sys.executable}" -m secure_browser.main'

    bat_path = os.path.join(os.path.dirname(installer_path), "run_update.bat")
    script = f"""@echo off
timeout /t 1 /nobreak > NUL
"{installer_path}" /SILENT /SUPPRESSMSGBOXES /NORESTART
start "" {relaunch_cmd}
del "%~f0"
"""
    try:
        with open(bat_path, "w") as f:
            f.write(script)
    except Exception:
        return

    subprocess.Popen([bat_path], shell=True)
    os._exit(0)


class AutoUpdater:
    """Thin backwards-compatible wrapper in case anything still imports the old class-based API."""
    check_for_update = staticmethod(check_for_update)
    download_installer = staticmethod(download_installer)
    launch_silent_install_and_relaunch = staticmethod(launch_silent_install_and_relaunch)
