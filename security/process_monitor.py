# -*- coding: utf-8 -*-
import os
import time
import threading
import psutil
from secure_browser.core.config import FORBIDDEN_APPS, SCREENSHOT_TOOLS

class ProcessSentinel(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.my_pid = os.getpid()
        self.parent_pid = os.getppid()
        self.process_cache = {}
        self.last_cleanup = time.time()
        self.running = True
        
        # Combine lists and normalize
        self.target_apps = set(x.lower() for x in FORBIDDEN_APPS) | set(x.lower() for x in SCREENSHOT_TOOLS)

    def stop(self):
        self.running = False

    def run(self):
        
        while self.running:
            try:
                current_time = time.time()
                
                # Health Check: Ensure the Parent Launcher is still alive!
                # If the student closes the app, the launcher dies. The Child must follow immediately.
                if not psutil.pid_exists(self.parent_pid):
                    os._exit(1)
                
                # Cleanup cache every 30s
                if current_time - self.last_cleanup > 30:
                    self.process_cache.clear()
                    self.last_cleanup = current_time

                # Fast scan
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        pid = proc.info['pid']
                        name = (proc.info['name'] or '').lower()
                        
                        # Skip self and parent
                        if pid in (self.my_pid, self.parent_pid):
                            continue
                        
                        # Skip python itself (often used for legitimate reasons) unless explicitly forbidden
                        if 'python' in name and 'python' not in self.target_apps:
                            continue

                        if name in self.target_apps:
                            # If we haven't killed this specific PID recently
                            if pid not in self.process_cache:
                                try:
                                    proc.kill()
                                    self.process_cache[pid] = current_time
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                                    
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                        
            except Exception as e:
                pass
                
            # Scan interval
            time.sleep(2.0)
