# -*- coding: utf-8 -*-
import sys
import os
 
# ─────────────────────────────────────────────────────────────────────────────
# CRITICAL: QTWEBENGINE_CHROMIUM_FLAGS **must** be set before ANY PyQt6 import.
# Chromium reads env-vars during the very first Qt/WebEngine library load.
# Setting them inside main() or run_child_process() is already too late.
# ─────────────────────────────────────────────────────────────────────────────
if "--secure-mode" in sys.argv:
    # Import only the plain config values — no Qt involved here yet.
    from secure_browser.core.config import QT_FLAGS, ALLOWED_DOMAINS
 
    # Exact origins (no wildcard ports — Chromium rejects those).
    _origins = ",".join(f"http://{d}" for d in ALLOWED_DOMAINS)
 
    _flags = (
        f"{QT_FLAGS} "
        f"--unsafely-treat-insecure-origin-as-secure={_origins} "
        f"--user-data-dir={os.path.join(os.environ.get('TEMP', 'C:/Windows/Temp'), 'SecureExamBrowserData')}"
    )
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags
    # Also set the Qt-level env vars before QApplication is constructed.
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
# ─────────────────────────────────────────────────────────────────────────────
 
import atexit
import ctypes
from ctypes import wintypes
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
 
from secure_browser.core.config import QT_FLAGS, APP_VERSION, ALLOWED_DOMAINS
from secure_browser.security.system_locker import sys_lock
from secure_browser.security.process_monitor import ProcessSentinel
from secure_browser.security.anti_debug import probe_environment, anti_debug_loop
from secure_browser.network.updater import AutoUpdater
from secure_browser.network.login_proxy import start_proxy, get_proxy_origin
from secure_browser.ui.main_window import SecureBrowser
 
# Windows API for Secure Desktop
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GENERIC_ALL = 0x10000000
 
class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)), ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)
    ]
 
class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)
    ]
 
def cleanup():
    """CRITICAL: Fail-safe cleanup to restore system state."""
    try:
        sys_lock.toggle_task_mgr(disable=False)
        sys_lock.remove_keyboard_hook()
    except Exception as e:
        pass
 
# Register cleanup to run on normal exit or crash (best effort)
atexit.register(cleanup)
 
def _build_chromium_flags() -> str:
    """Build the full Chromium flags string used by the child browser process."""
    origins = ",".join(f"http://{d}" for d in ALLOWED_DOMAINS)
    return (
        f"{QT_FLAGS} "
        f"--unsafely-treat-insecure-origin-as-secure={origins} "
        f"--user-data-dir={os.path.join(os.environ.get('TEMP', 'C:/Windows/Temp'), 'SecureExamBrowserData')}"
    )
 
def launch_secure_desktop():
    desktop_name = "SecureExamDesktop"
    original_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
 
    # ── CRITICAL: set env vars BEFORE CreateProcessW ────────────────────────
    # The child process inherits the parent's environment block.  This means
    # QTWEBENGINE_CHROMIUM_FLAGS is present from the very first byte of the
    # child's execution — before Python loads, before any DLL is mapped.
    # Every other approach (setting it inside the child, sys.argv injection)
    # can race against Qt library initialisation.
    _cf = _build_chromium_flags()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _cf
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
 
    # 1. Disable Task Manager in parent
    sys_lock.toggle_task_mgr(disable=True)
 
    try:
        h_desk = user32.CreateDesktopW(desktop_name, None, None, 0, GENERIC_ALL, None)
        if not h_desk:
            raise Exception("Failed to create secure desktop")
 
        si = STARTUPINFO()
        si.cb = ctypes.sizeof(STARTUPINFO)
        si.lpDesktop = desktop_name
        pi = PROCESS_INFORMATION()
 
        # Determine command to run self in secure mode
        # Determine command to run self in secure mode
        is_frozen = getattr(sys, 'frozen', False)
        # Fallback: check if running as .exe (Nuitka sometimes misses sys.frozen or we are in a weird state)
        if not is_frozen and os.path.basename(sys.argv[0]).lower().endswith(".exe"):
            is_frozen = True
 
 
        if is_frozen:
            # Use the executable itself
            cmd = f'"{os.path.abspath(sys.argv[0])}" --secure-mode'
        else:
            # Dev mode: use python interpreter
            cmd = f'"{sys.executable}" -m secure_browser.main --secure-mode'
 
        success = kernel32.CreateProcessW(
            None, cmd, None, None, False, 0, None, None,
            ctypes.byref(si), ctypes.byref(pi)
        )
        
        if success:
            user32.SwitchDesktop(h_desk)
            # Wait for child process to finish
            kernel32.WaitForSingleObject(pi.hProcess, 0xFFFFFFFF)
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)
        else:
            raise Exception(f"CreateProcessW failed: {ctypes.GetLastError()}")
            
    except Exception as e:
        pass
    finally:
        # ALWAYS restore desktop and unlock system
        user32.SwitchDesktop(original_desktop)
        cleanup()
 
def run_child_process():
    """Runs inside the secure desktop."""
    try:
        
        # 1. Install Hook (only if frozen/compiled for safety)
        if getattr(sys, 'frozen', False):
            sys_lock.install_keyboard_hook()
        
        # 2. Start Sentinel
        sentinel = ProcessSentinel()
        sentinel.start()

        # 2.1 Start continuous anti-debug watch (one process scan per minute).
        import threading
        threading.Thread(
            target=anti_debug_loop, args=(60.0,), daemon=True, name="AntiDebug"
        ).start()

        # 2.5 Start the Local Proxy Server BEFORE Qt initialization
        allocated_port = start_proxy()
        
        # 3. Launch UI
        if hasattr(Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
 
        # ── Diagnostic: confirm the env var was inherited from the parent ────
        _inherited_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "<NOT SET>")
 
        # ── THE ACTUAL FIX: INJECT CHROMIUM FLAGS DIRECTLY INTO SYS.ARGV ────
        # Chromium reads from sys.argv before QApplication is fully constructed.
        # By injecting the flags into sys.argv, we guarantee Chromium sees them
        # regardless of OS-level environment variable inheritance issues.
        # We also treat the dynamic proxy origin as secure.
        proxy_origin = get_proxy_origin()
        origins_list = [f"http://{d}" for d in ALLOWED_DOMAINS]
        if proxy_origin:
            origins_list.append(proxy_origin)
        _origins = ",".join(origins_list)
        
        _injected_flags = QT_FLAGS.split() if QT_FLAGS else []
        _injected_flags.append(f"--unsafely-treat-insecure-origin-as-secure={_origins}")
        _injected_flags.append(f"--user-data-dir={os.path.join(os.environ.get('TEMP', 'C:/Windows/Temp'), 'SecureExamBrowserData')}")
        _injected_flags.append("--enable-media-stream")
        _injected_flags.append("--use-fake-ui-for-media-stream")
        
        sys.argv.extend(_injected_flags)
 
        app = QApplication(sys.argv)
        app.setApplicationName("Secure Exam Browser")
        browser = SecureBrowser(proxy_origin)
        browser.showFullScreen()
        
        exit_code = app.exec()
        
        # 4. Cleanup child specific
        sentinel.stop()
        sys_lock.remove_keyboard_hook()
        
        sys.exit(exit_code)
        
    except Exception as e:
        sys.exit(1)
 
def show_error(msg):
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, msg, "Secure Browser Error", 0x10)
    else:
        print(msg, file=sys.stderr)
 
h_mutex = None
 
def enforce_single_instance():
    """Ensure only one instance of the application launcher can run at a time."""
    global h_mutex
    # Create an OS-level lock that survives even if the app crashes
    mutex_name = "Global\\SecureExamBrowser_Mutex_2026_xYz"
    h_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    last_error = kernel32.GetLastError()
    
    # 183 == ERROR_ALREADY_EXISTS -> Mutex already held by another instance
    if last_error == 183:  
        return False
    return True
 
def check_integrity():
    """Verify application integrity to prevent tampering."""
    # Only consider it compiled if sys.frozen is True, or if the actual script file invoked was our compiled .exe
    is_frozen = getattr(sys, 'frozen', False) or (os.path.basename(sys.argv[0]).lower() in ['main.exe', 'securebrowser.exe'])
    if is_frozen and sys.platform == "win32":
        exe_path = os.path.abspath(sys.argv[0])
        exe_dir = os.path.dirname(exe_path)
        
        # 1. Anti-Tamper: Ensure we are running from a full standalone environment 
        # (Nuitka creates python3*.dll in the dir). This catches users moving just the .exe
        import glob
        if not glob.glob(os.path.join(exe_dir, "python3*.dll")):
            msg = "Integrity Check Failed:\n\nThe application files have been tampered with or improperly extracted. Missing crucial engine files.\nPlease reinstall the Secure Exam Browser."
            show_error(msg)
            sys.exit(1)
            
        # 2. Prevent running from Temporary Directories (common for extraction bypasses)
        temp_dir = os.environ.get('TEMP', '').lower()
        if temp_dir and temp_dir in exe_path.lower():
            msg = "Integrity Check Failed:\n\nRunning from the Temporary directory is not allowed.\nPlease install the application properly."
            show_error(msg)
            sys.exit(1)
 
def main():
    
    # 0. Self-Integrity Verification
    check_integrity()
    
    # 1. Anti-Debug Check (One-off)
    ok, reasons = probe_environment()
    if not ok:
        msg = "Security Breach Detected:\n\n" + "\n".join(reasons)
        show_error(msg)
        sys.exit(1)
 
    # 1.5. Single Instance Check (Launcher only)
    # This prevents the 5x clicks from becoming 5x Chromium Engines loading
    if "--secure-mode" not in sys.argv:
        if not enforce_single_instance():
            # Fail silently or with a non-intrusive error so Windows doesn't lock up
            sys.exit(0)
 
    # 2. Update Check (Parent only)
    if "--secure-mode" not in sys.argv:
        AutoUpdater.check_and_update()
 
    # 3. Mode Selection
    if "--secure-mode" in sys.argv:
        run_child_process()
    else:
        launch_secure_desktop()
 
if __name__ == "__main__":
    main()
 