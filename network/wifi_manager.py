# -*- coding: utf-8 -*-
import time
import threading
from PyQt6.QtCore import pyqtSignal, QObject
import pywifi
from pywifi import const

class WiFiManager(QObject):
    scan_complete = pyqtSignal(list)
    connect_complete = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._interface = None
        self._init_interface()

    def _init_interface(self):
        try:
            wifi = pywifi.PyWiFi()
            ifaces = wifi.interfaces()
            if ifaces:
                self._interface = ifaces[0]
            else:
                pass
        except Exception as e:
            pass

    def scan_async(self):
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        if not self._interface:
            self.scan_complete.emit(["No Wi-Fi Adapter"])
            return
            
        try:
            self._interface.scan()
            time.sleep(3)
            results = self._interface.scan_results()
            
            # Filter and sort unique SSIDs
            ssids = sorted({r.ssid for r in results if r.ssid.strip()})
            self.scan_complete.emit(ssids if ssids else ["No Networks Found"])
            
        except Exception as e:
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
            self.connect_complete.emit(False, f"Error: {str(e)}")
