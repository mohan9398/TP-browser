# `security/` — System Lockdown & Anti-Cheat Layer

This folder is the **enforcement** core of the Secure Exam Browser. Its job is to
make the student's machine a controlled environment for the duration of the exam:
detect debugging/virtual-machine tampering, kill prohibited applications, and
block the keyboard/OS shortcuts a student could use to escape or cheat.

## Files at a glance

| File | Responsibility |
|------|----------------|
| `anti_debug.py` | Detects debuggers, reverse-engineering tools, and virtual machines. |
| `process_monitor.py` | Periodically scans for and kills forbidden / screen-capture apps. |
| `system_locker.py` | Disables Task Manager and blocks escape-hatch keyboard shortcuts. |

---

## `anti_debug.py` — anti-debugging & anti-VM detection

This module checks whether the app is running in a "hostile" analysis environment.
It is **hardened and obfuscated** so an attacker reading the binary cannot easily
see what it looks for.

**String obfuscation** — the names of debuggers (`gdb`, `x64dbg`, `ollydbg`,
`ida`, `wireshark`, `cheatengine`, …), VM tools (`vboxservice`, `vmtoolsd`,
`vmware`, `qemu-ga`, …), and VM marker keywords (`VirtualBox`, `VMware`, `KVM`,
`QEMU`, `Hyper-V`, …) are stored as **base64** and decoded at runtime by `_ds()`.
Reading the source/binary therefore reveals nothing obvious.

**Detection techniques:**

- **`_scan_for_targets()` / `_scan_process_list()`** — walk the running process
  list looking for debugger and VM-tool process names. `_scan_for_targets()` does
  a *single* pass matching both lists at once to keep CPU cost low.
- **`IsDebuggerPresent`** — calls the Windows API directly to detect a debugger
  attached to the process.
- **`_check_windows_registry()`** — reads BIOS / System registry keys (paths
  themselves stored base64-encoded) and looks for VM marker strings, exposing
  VMs even when no VM tools are running.
- **`_check_mac_address()`** — checks for known VMware/VirtualBox/Hyper-V MAC
  address prefixes. **(Currently disabled** in `_collect_vm_reasons()` because
  installing VirtualBox adds host-only adapters to *physical* PCs and caused false
  positives.)

**How results are used:**

- **`probe_environment()`** — the non-fatal one-shot check. Returns
  `(ok, reasons)`. `main.py` calls this at startup and shows the reasons in a
  message box before exiting if anything is found.
- **`anti_debug_loop(interval=60)`** — runs in a background daemon thread inside
  the secure child, re-checking roughly once a minute (with random jitter so the
  timing is unpredictable) and hard-exiting if a debugger/VM appears mid-exam.
- **`check_debugger()` / `check_vm()` / `initialize()`** — convenience entry
  points that **hard-exit** (`_fatal_exit`) on detection.
- **`_fatal_exit()`** — shows a clear Windows message box explaining *why* the
  browser closed (so a legitimate student knows to close their VM/debugger), then
  forcibly terminates with `os._exit(1)`. A small random `_sleep_jitter()` makes
  timing attacks harder.
- **`DEBUG` / `_dbg()`** — optional diagnostic logging gated behind the
  `TELE_BROWSER_DEBUG` environment variable.

---

## `process_monitor.py` — the Process Sentinel

`ProcessSentinel` is a background daemon **thread** that polices what else is
running on the machine during the exam.

**What it does, in a loop:**

1. **Parent health check** — verifies the launcher (parent) process is still
   alive via `psutil.pid_exists`. If the launcher dies, the child follows with
   `os._exit(1)` on the next scan, which can be up to roughly 59 seconds later.
   This prevents a long-lived orphaned exam window.
2. **Scan & kill** — walks the process list and, if it finds a process whose name
   is in the blocklist, kills it. The blocklist combines `FORBIDDEN_APPS`
   (other browsers, Discord/Slack/Telegram/Zoom, AnyDesk/TeamViewer, regedit, …)
   and `SCREENSHOT_TOOLS` (Snipping Tool, OBS, Bandicam, ShareX, Lightshot, …)
   from the config.
3. **Safety guards** — it never kills itself or the parent, and it skips generic
   `python` processes (unless explicitly blocked) to avoid self-termination
   during development.
4. **Kill cache** — a `process_cache` remembers recently killed PIDs (cleared
   every 30s) so it does not waste effort re-killing the same process every tick.

The scan runs about once per minute (`time.sleep(59.0)`) to keep CPU usage
negligible on low-end exam machines. `stop()` ends the loop cleanly on shutdown.

---

## `system_locker.py` — keyboard & Task Manager lockdown

`SystemLocker` (exposed as the global `sys_lock`) blocks the common ways a student
could escape the locked browser. It talks directly to the Windows API via
`ctypes`.

**Capabilities:**

- **`toggle_task_mgr(disable=True)`** — sets the `DisableTaskMgr` policy in the
  registry (`HKCU\...\Policies\System`). The launcher disables it on start and
  `cleanup()` re-enables it on exit. *Designed to be wrapped in try/finally so the
  machine is always restored.*
- **`install_keyboard_hook()`** — installs a **low-level keyboard hook**
  (`WH_KEYBOARD_LL`) so it sees keystrokes before the OS does. A reference to the
  callback is kept on `self` to stop Python's garbage collector from freeing it.
- **`hook_proc()`** — the hook callback that decides which keys to swallow:
  - **Windows keys** (left/right) — blocked.
  - **Alt+Tab, Alt+Esc, Alt+F4, Alt+Space** — blocked (no task switching, no
    force-close, no window menu).
  - **Ctrl+Shift+Esc** — blocked (the Task Manager shortcut).
  - Everything else is passed through with `CallNextHookEx`.
- **`remove_keyboard_hook()`** — uninstalls the hook so normal keyboard behaviour
  returns when the exam ends.

The `KBDLLHOOKSTRUCT` structure and the manual `ULONG_PTR` definition exist to
correctly interpret the raw keyboard event data the OS hands to the hook.

---

## How the security layer ties together

- At startup `main.py` runs `probe_environment()` (anti-debug/VM gate).
- The launcher calls `sys_lock.toggle_task_mgr(disable=True)` and, in the child,
  `sys_lock.install_keyboard_hook()`.
- The child starts a `ProcessSentinel` and the `anti_debug_loop` thread for
  continuous protection.
- On the normal parent cleanup path, `cleanup()` re-enables Task Manager and
  removes the hook. The `finally` and `atexit` handlers provide best-effort
  restoration, but cannot run after every possible hard process termination or
  system failure.

> **Note:** This layer is **Windows-specific** — it relies on `winreg`, `ctypes`
> Windows DLLs, and Windows process semantics. Most of it no-ops or is skipped on
> other platforms.
