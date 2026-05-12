# -*- coding: utf-8 -*-
import sys
import os
import json
import shutil
import urllib.request
import subprocess
from secure_browser.core.config import APP_VERSION, UPDATE_CHECK_URL

class AutoUpdater:
    CHECK_TIMEOUT = 10
    DOWNLOAD_TIMEOUT = 300 

    @staticmethod
    def _version_tuple(v: str):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except Exception:
            return (0,)

    @staticmethod
    def check_and_update():
        # Only update if running as a compiled executable
        executable = sys.executable.lower()
        argv0 = sys.argv[0].lower()
        is_frozen = (
            getattr(sys, "frozen", False) or 
            executable.endswith("main.exe") or 
            executable.endswith("securebrowser.exe") or
            argv0.endswith("main.exe") or
            argv0.endswith("securebrowser.exe")
        )
        if not is_frozen:
            return

        
        try:
            # Use custom user agent
            headers = {"User-Agent": "SecureExamBrowser-Updater"}
            req = urllib.request.Request(UPDATE_CHECK_URL, headers=headers)
            
            with urllib.request.urlopen(req, timeout=AutoUpdater.CHECK_TIMEOUT) as resp:
                data = resp.read()
                
            payload = json.loads(data.decode("utf-8"))
            
            latest_version = payload.get("version", "").strip()
            download_url = payload.get("url", "").strip()
            
            if not latest_version or not download_url:
                return

            current_ver = AutoUpdater._version_tuple(APP_VERSION)
            remote_ver = AutoUpdater._version_tuple(latest_version)

            if remote_ver > current_ver:
                AutoUpdater._perform_update(download_url)
            else:
                pass

        except Exception as e:
            pass

    @staticmethod
    def _perform_update(url: str):
        current_exe = os.path.abspath(sys.argv[0])
        target_path = os.path.join(os.path.dirname(current_exe), "TeleBrowser_New.exe")
        
        try:
            with urllib.request.urlopen(url, timeout=AutoUpdater.DOWNLOAD_TIMEOUT) as resp, open(target_path, "wb") as f:
                shutil.copyfileobj(resp, f)
                
            
            # Create batch script to swap files
            AutoUpdater._create_swap_script(target_path)
            
        except Exception as e:
            pass

    @staticmethod
    def _create_swap_script(new_exe_path):
        current_exe = os.path.abspath(sys.argv[0])
        base_dir = os.path.dirname(current_exe)
        bat_path = os.path.join(base_dir, "update.bat")
        
        script = f"""@echo off
timeout /t 2 /nobreak > NUL
del "{current_exe}"
move "{new_exe_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
        try:
            with open(bat_path, "w") as f:
                f.write(script)
                
            # Execute and exit
            subprocess.Popen([bat_path], shell=True)
            sys.exit(0)
        except Exception as e:
            pass
