# -*- coding: utf-8 -*-
import sys
import time
import threading
import subprocess
from PyQt6.QtCore import pyqtSignal, QObject
import pywifi
from pywifi import const
from secure_browser.core.logger import get_logger

log = get_logger(__name__)

class WiFiManager(QObject):
    scan_complete = pyqtSignal(list)
    connect_complete = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._interface = None
        self._cancel_scan = threading.Event()
        self._init_interface()

    def _init_interface(self):
        try:
            wifi = pywifi.PyWiFi()
            ifaces = wifi.interfaces()
            if ifaces:
                self._interface = ifaces[0]
            else:
                log.warning("No Wi-Fi interface found")
        except Exception:
            log.exception("Failed to initialise Wi-Fi interface")

    def get_saved_ssids(self) -> set:
        """Return the set of SSIDs that already have a saved profile on this PC.

        These can be reconnected with one click — the OS already holds the
        credentials, so no password needs to be entered or shown.
        """
        if not self._interface:
            return set()
        try:
            return {p.ssid for p in self._interface.network_profiles() if p.ssid}
        except Exception:
            return set()

    @staticmethod
    def get_current_ssid() -> str:
        """Windows-only: return the SSID of the currently connected network.

        Uses `netsh wlan show interfaces` — unlike the saved-password lookup
        this does not require admin rights. Returns "" if not connected or
        the query fails for any reason (no Wi-Fi adapter, ethernet-only, etc).
        """
        if sys.platform != "win32":
            return ""
        try:
            CREATE_NO_WINDOW = 0x08000000  # don't flash a console window
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                stderr=subprocess.DEVNULL, text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            for line in out.splitlines():
                line = line.strip()
                # Match "SSID" but not "BSSID"
                if line.startswith("SSID") and not line.startswith("BSSID"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            log.exception("Could not read current SSID")
        return ""

    @staticmethod
    def get_saved_password(ssid: str) -> str:
        """Windows-only: return the stored password for a saved network.

        Uses `netsh wlan show profile name=<ssid> key=clear`. Note: Windows
        only reveals the key when the process is running elevated (admin);
        otherwise an empty string is returned.
        """
        if sys.platform != "win32" or not ssid:
            return ""
        try:
            CREATE_NO_WINDOW = 0x08000000  # don't flash a console window
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
                stderr=subprocess.DEVNULL, text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            for line in out.splitlines():
                if "Key Content" in line:
                    return line.split(":", 1)[1].strip()
        except Exception:
            log.exception("Could not read saved password for %s", ssid)
        return ""

    def cancel_scan(self):
        """Abort an in-flight scan; the worker stops before emitting results."""
        self._cancel_scan.set()

    def scan_async(self):
        self._cancel_scan.clear()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        if not self._interface:
            self.scan_complete.emit(["No Wi-Fi Adapter"])
            return

        try:
            self._interface.scan()
            # Wait ~3s for results, but in small slices so the dialog can
            # cancel the scan promptly instead of being stuck for the full wait.
            for _ in range(30):
                if self._cancel_scan.is_set():
                    log.debug("Wi-Fi scan cancelled")
                    return
                time.sleep(0.1)

            if self._cancel_scan.is_set():
                return

            results = self._interface.scan_results()

            # Filter and sort unique SSIDs
            ssids = sorted({r.ssid for r in results if r.ssid.strip()})
            self.scan_complete.emit(ssids if ssids else ["No Networks Found"])

        except Exception:
            log.exception("Wi-Fi scan failed")
            self.scan_complete.emit(["Scan Failed"])

    def connect_async(self, ssid: str, password: str):
        threading.Thread(target=self._connect_worker, args=(ssid, password), daemon=True).start()

    def _connect_worker(self, ssid: str, password: str):
        if not self._interface:
            self.connect_complete.emit(False, "No Wi-Fi Adapter")
            return

        try:
            
            # 1. Disconnect current
            self._interface.disconnect()
            time.sleep(1)

            # 2. Check if profile exists
            profile = None
            # Don't delete all! Just check if we have one for this ssid
            existing_profiles = self._interface.network_profiles()
            for p in existing_profiles:
                if p.ssid == ssid:
                    profile = p
                    break
            
            # If not found or we want to overwrite with new password
            if not profile:
                profile = pywifi.Profile()
                profile.ssid = ssid
                profile.auth = const.AUTH_ALG_OPEN
                
                if password:
                    profile.akm.append(const.AKM_TYPE_WPA2PSK)
                    profile.cipher = const.CIPHER_TYPE_CCMP
                    profile.key = password
                else:
                    profile.akm.append(const.AKM_TYPE_NONE)
                    profile.cipher = const.CIPHER_TYPE_NONE
                
                profile = self._interface.add_network_profile(profile)
            
            # 3. Connect
            self._interface.connect(profile)
            
            # 4. Wait for connection (Increased timeout to 15s)
            for _ in range(30):
                if self._interface.status() == const.IFACE_CONNECTED:
                    # Connection established, wait a bit for DHCP
                    time.sleep(2) 
                    self.connect_complete.emit(True, "Connected successfully")
                    return
                time.sleep(0.5)
                
            self.connect_complete.emit(False, "Connection timeout (Check password?)")

        except Exception as e:
            log.exception("Wi-Fi connect to %s failed", ssid)
            self.connect_complete.emit(False, f"Error: {str(e)}")
