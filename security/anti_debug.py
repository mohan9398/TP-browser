

# -*- coding: utf-8 -*-
"""
Anti-debugging and anti-VM detection module for Tele Browser
(Hardened Windows Version — Obfuscated & Optimized)
"""

import os
import sys
import time
import psutil
import base64
import random
import threading
import ctypes

# Try to import Windows Registry module
try:
    import winreg
except ImportError:
    winreg = None

# === Debug helpers ==========================================================
DEBUG = os.environ.get("TELE_BROWSER_DEBUG", "").lower() in {"1", "true", "yes", "on"}

def _dbg(msg: str) -> None:
    if not DEBUG: return
    try: print(f"[ANTI-DEBUG] {msg}", file=sys.stderr)
    except: pass

# === String obfuscation helpers ============================================
def _ds(b64: str) -> str:
    """Decode a base64-encoded UTF-8 string."""
    return base64.b64decode(b64).decode("utf-8", errors="ignore")

# --- Obfuscated Strings (Decoded at runtime) ---
# Processes (Debuggers)
_B64_DBG_PROCS = (
    "Z2Ri", "bGxkYg==", "c3RyYWNl", "bHRyYWNl", "cmFkYXJlMg==", "cjI=", 
    "aWRh", "aWRhNjQ=", "eDY0ZGJn", "b2xseWRiZw==", "d2luZGJn", "cHlkZXZk", 
    "ZGVidWducHk=", "Y2hlYXRlbmdpbmU=", "cHJvY2Vzc2hhY2tlcg==", "aHR0cGRlYnVnZ2Vy", "d2lyZXNoYXJr"
)

# Processes (VM Tools)
_B64_VM_PROCS = (
    "dmJveHNlcnZpY2U=", "dmJveHRyYXk=", "dm10b29sc2Q=", "dm13YXJl", 
    "cWVtdS1nYQ==", "cHJsX3Rvb2xz", "eGVuc3RvcmVk", "dm13YXJlIHVzZXI=", 
    "dm13YXJlIHRyYXk="
)

# VM Keywords
_B64_VM_MARKERS = (
    "VmlydHVhbEJveA==", "Vk13YXJl", "S1ZN", "UUVNVQ==", "SHlwZXItVg==", 
    "UGFyYWxsZWxz", "WGVu", "Qm9jaHM=", "VHJpYWw="
)

# Registry Paths
_B64_WIN_REG_BIOS = "SEFSRFdBUkVcREVTQ1JJUFRJT05cU3lzdGVtXEJJT1M=" 
_B64_WIN_REG_SYS  = "SEFSRFdBUkVcREVTQ1JJUFRJT05cU3lzdGVt"      

# Decode constants
_DEBUGGER_NAMES = tuple(_ds(s) for s in _B64_DBG_PROCS)
_VM_PROCESSES   = tuple(_ds(s) for s in _B64_VM_PROCS)
_VM_MARKERS     = tuple(_ds(s) for s in _B64_VM_MARKERS)
_REG_BIOS       = _ds(_B64_WIN_REG_BIOS)
_REG_SYS        = _ds(_B64_WIN_REG_SYS)

_VM_MAC_PREFIXES = (
    "00:05:69", "00:0C:29", "00:1C:14", "00:50:56", # VMware
    "08:00:27", # VirtualBox
    "00:03:FF", "00:15:5D"  # Hyper-V
)

# === Core Logic ============================================================

def _sleep_jitter(min_ms: int = 10, max_ms: int = 50) -> None:
    try: time.sleep(random.uniform(min_ms/1000.0, max_ms/1000.0))
    except: pass

# def _fatal_exit(reason: str = "unknown") -> None:
#     """Force kill the app immediately."""
#     _sleep_jitter()
#     if DEBUG: print(f"[FATAL] {reason}", file=sys.stderr)
#     try:
#         # Forceful exit
#         os._exit(1) 
#     except:
#         sys.exit(1)
def _fatal_exit(reason: str = "unknown") -> None:
    """Force kill the app after showing a clear message to the user."""
    _sleep_jitter()
    if DEBUG:
        try:
            print(f"[FATAL] {reason}", file=sys.stderr)
        except Exception:
            pass

    # Show on-screen message (Windows) so student knows why it closed.
    try:
        msg = (
            "Secure Exam Browser cannot run in this environment.\n\n"
            f"Reason:\n{reason}\n\n"
            "Please close any debuggers or virtual machine software and then "
            "start the browser again."
        )

        if sys.platform == "win32":
            # MB_ICONHAND (0x10) | MB_OK (0x0)
            ctypes.windll.user32.MessageBoxW(
                None,
                msg,
                "Secure Exam Browser - Security Violation",
                0x00000010,
            )
        else:
            # Fallback for non-Windows (just in case)
            print(msg, file=sys.stderr)
    except Exception:
        pass

    try:
        os._exit(1)
    except Exception:
        sys.exit(1)


def _scan_process_list(targets: tuple) -> str:
    """Returns the name of the matched target process if found, else empty string."""
    for proc in psutil.process_iter(['name']):
        try:
            pname = proc.info['name'].lower() if proc.info['name'] else ""
            for t in targets:
                if t in pname:
                    return pname
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return ""

def _check_windows_registry() -> bool:
    if not winreg: return False
    
    suspicious = False
    keys_to_check = [
        (_REG_BIOS, "SystemManufacturer"),
        (_REG_BIOS, "SystemProductName"),
        (_REG_SYS,  "SystemManufacturer"),
        (_REG_SYS,  "Model")
    ]

    for reg_path, key_name in keys_to_check:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            val, _ = winreg.QueryValueEx(key, key_name)
            winreg.CloseKey(key)
            
            val_lower = str(val).lower()
            for marker in _VM_MARKERS:
                if marker.lower() in val_lower:
                    suspicious = True
        except Exception:
            pass
            
    return suspicious

def _check_mac_address() -> bool:
    try:
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.address:
                    mac = snic.address.upper().replace("-", ":")
                    for prefix in _VM_MAC_PREFIXES:
                        if mac.startswith(prefix):
                            return True
    except: pass
    return False
def _collect_debugger_reasons() -> list:
    """Non-fatal debugger detection. Returns list of human-readable reasons."""
    reasons = []

    # 1) Known debugger processes
    found_dbg = _scan_process_list(_DEBUGGER_NAMES)
    if found_dbg:
        reasons.append(
            f"Debugger / reverse engineering tool detected ({found_dbg})."
        )

    # 2) IsDebuggerPresent API
    if sys.platform == "win32":
        try:
            if ctypes.windll.kernel32.IsDebuggerPresent():
                reasons.append("A debugger is attached to this process (IsDebuggerPresent = TRUE).")
        except Exception:
            pass

    return reasons


def _collect_vm_reasons() -> list:
    """Non-fatal VM detection. Returns list of human-readable reasons."""
    reasons = []

    # 1) MAC prefixes that belong to VMware/VirtualBox/Hyper-V
    # DISABLED: This causes false positives on physical host machines because 
    # installing VirtualBox creates "Host-Only" network adapters on the physical PC.
    # if _check_mac_address():
    #     reasons.append("Virtual machine network adapter detected (VM MAC prefix found).")
    # 2) VM tooling processes (VMware Tools, VBoxService, etc.)
    found_vm = _scan_process_list(_VM_PROCESSES)
    if found_vm:
        reasons.append(f"Virtualization tools running ({found_vm}). Please close Docker, WSL, or VM software.")

    # 3) BIOS / System strings in registry that indicate VM hardware
    if sys.platform == "win32" and _check_windows_registry():
        reasons.append("BIOS / System strings indicate a virtual machine (VM markers in registry).")

    return reasons


def probe_environment():
    """
    Non-fatal one-shot check.

    Returns:
        (ok: bool, reasons: list[str])

    ok      = True  → Environment is clean.
    ok      = False → At least one debugger / VM indicator found.
    reasons = list of human-readable explanations to show to the user or log.
    """
    reasons = []
    reasons.extend(_collect_debugger_reasons())
    reasons.extend(_collect_vm_reasons())

    ok = not reasons
    _dbg(f"probe_environment -> ok={ok}, reasons={reasons}")
    return ok, reasons


# === Public API ============================================================

# def check_debugger() -> bool:
#     """Checks for debuggers attached or running."""
#     if _scan_process_list(_DEBUGGER_NAMES):
#         _fatal_exit("Debugger Process Found")
#         return True
    
#     if sys.platform == "win32":
#         try:
#             if ctypes.windll.kernel32.IsDebuggerPresent():
#                 _fatal_exit("IsDebuggerPresent() = True")
#                 return True
#         except: pass
        
#     return False
def check_debugger() -> bool:
    """Checks for debuggers attached or running. Exits on detection."""
    reasons = _collect_debugger_reasons()
    if reasons:
        _fatal_exit(" | ".join(reasons))
        return True
    return False

# def check_vm() -> bool:
#     """Checks for Virtual Machine environment."""
#     suspicious = False
    
#     if _check_mac_address(): 
#         suspicious = True
        
#     if _scan_process_list(_VM_PROCESSES): 
#         suspicious = True
        
#     if sys.platform == "win32" and _check_windows_registry(): 
#         suspicious = True

#     if suspicious:
#         _fatal_exit("Virtual Machine Detected")
#         return True
        
#     return False
def check_vm() -> bool:
    """Checks for Virtual Machine environment. Exits on detection."""
    reasons = _collect_vm_reasons()
    if reasons:
        _fatal_exit(" | ".join(reasons))
        return True
    return False


def anti_debug_loop(interval: float = 5.0) -> None:
    """Run this in a background thread."""
    while True:
        check_debugger()
        check_vm()
        time.sleep(5.0 + random.uniform(-1.0, 1.5))

# def initialize():
#     check_debugger()
#     check_vm()
def initialize():
    """
    Backwards-compatible entry point.

    Still used by other code paths that want "hard exit on detection".
    """
    ok, reasons = probe_environment()
    if not ok:
        _fatal_exit(" | ".join(reasons))
