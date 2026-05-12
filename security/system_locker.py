# -*- coding: utf-8 -*-
import sys
import ctypes
import winreg
from ctypes import wintypes

# Some Python versions don't define ULONG_PTR in wintypes; define if missing
if not hasattr(wintypes, "ULONG_PTR"):
    if ctypes.sizeof(ctypes.c_void_p) == ctypes.sizeof(ctypes.c_uint64):
        wintypes.ULONG_PTR = ctypes.c_uint64
    else:
        wintypes.ULONG_PTR = ctypes.c_ulong

# Windows API Constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
LLKHF_ALTDOWN = 0x20

# Structures
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]

class SystemLocker:
    def __init__(self):
        self.hook = None
        self.user32 = ctypes.windll.user32
        self.callback_func = None # Keep ref to prevent GC

    def toggle_task_mgr(self, disable=True):
        """
        Safely toggles Task Manager. 
        Wrap in try-finally in main app to ensure Restoration.
        """
        val = 1 if disable else 0
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
        
        try:
            # CreateKey opens or creates. We need appropriate access.
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            
            # Set DisableTaskMgr
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, val)
            winreg.CloseKey(key)
            
            state = "DISABLED" if disable else "ENABLED"
            
        except Exception as e:
            pass

    def hook_proc(self, nCode, wParam, lParam):
        if nCode == 0 and (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN):
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = kb.vkCode

            # Block Windows keys (Left=91, Right=92)
            if vk in (91, 92):
                return 1

            # Check for ALT combinations
            alt_down = (kb.flags & LLKHF_ALTDOWN) != 0
            if alt_down:
                # Block Alt+Tab (9), Alt+Esc (27), Alt+F4 (115), Alt+Space (32)
                if vk in (9, 27, 115, 32):
                    return 1

            # Block Ctrl+Shift+Esc (Task Manager bypass)
            if vk == 27: # Escape key
                ctrl_down = (self.user32.GetAsyncKeyState(17) & 0x8000) != 0 # VK_CONTROL = 17
                shift_down = (self.user32.GetAsyncKeyState(16) & 0x8000) != 0 # VK_SHIFT = 16
                if ctrl_down and shift_down:
                    return 1

        return self.user32.CallNextHookEx(self.hook, nCode, wParam, lParam)

    def install_keyboard_hook(self):
        """Installs low-level keyboard hook to block special keys."""
        try:
            # Define callback type
            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            self.callback_func = HOOKPROC(self.hook_proc)
            
            # Get module handle (NULL for current process)
            h_mod = ctypes.windll.kernel32.GetModuleHandleW(None)
            
            # Install hook
            self.hook = self.user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.callback_func, h_mod, 0)
            
            if not self.hook:
                pass
            else:
                pass
                
        except Exception as e:
            pass

    def remove_keyboard_hook(self):
        if self.hook:
            self.user32.UnhookWindowsHookEx(self.hook)
            self.hook = None

# Global instance
sys_lock = SystemLocker()
