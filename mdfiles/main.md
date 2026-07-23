# `main.py` — Application Entry Point & Launcher

This is the **starting point** of the Secure Exam Browser. It is responsible for
deciding *how* the application runs, locking down the machine, spawning the actual
browser inside an isolated desktop, and restoring the system on the normal
cleanup paths. Everything else in the project (network, security, ui) is wired
together from here.

---

## The big picture: two processes, two modes

The application deliberately runs as **two separate processes**:

1. **The Launcher (parent)** — the process started when the student double-clicks
   the app. It performs security pre-checks, locks the system, creates a brand new
   isolated Windows desktop, and then launches a *second copy of itself* inside
   that desktop.
2. **The Secure Child (`--secure-mode`)** — the second copy. It runs on the
   isolated desktop and actually shows the exam browser window.

The mode is selected by looking for the `--secure-mode` flag in `sys.argv`.

```
Student clicks app
        │
        ▼
   Launcher (parent)  ── integrity + anti-debug checks
        │             ── single-instance lock
        │             ── auto-update check
        │             ── lock system (disable Task Manager)
        │             ── create "SecureExamDesktop"
        │
        ▼  CreateProcessW("...--secure-mode")
   Secure Child  ───── keyboard hook + process sentinel
                 ───── anti-debug background loop
                 ───── local login proxy
                 ───── full-screen exam browser (Qt UI)
```

---

## Critical detail: Chromium flags must be set first

The very top of the file (before *any* PyQt6 import) checks for `--secure-mode`
and sets the `QTWEBENGINE_CHROMIUM_FLAGS` environment variable. This is
intentional and load-bearing:

- Chromium (the engine behind Qt WebEngine) reads these flags **once**, during
  the first Qt/WebEngine library load.
- If you set them later (inside `main()` or after importing PyQt6) it is already
  too late and they are ignored.

The flags treat the internal exam origins as "secure", and point the browser at a
dedicated user-data directory under the Windows TEMP folder.

---

## Key functions

### `cleanup()`
A **fail-safe** that restores the system to a usable state: re-enables Task
Manager and removes the low-level keyboard hook. It is registered with
`atexit.register(cleanup)` so it runs on a normal exit *or* a crash (best effort).
This reduces the risk of leaving a student's machine locked after an unexpected
failure. Like any in-process cleanup, it cannot run after every hard termination
or operating-system failure.

### `_build_chromium_flags()`
Builds the full Chromium command-line flag string (allowed origins + user-data
directory) used by the child process.

### `launch_secure_desktop()` — the heart of the launcher
1. Sets the Chromium env vars **before** spawning the child, so the child
   inherits them from the very first byte of execution (avoiding race conditions).
2. Disables Task Manager via the system locker.
3. Creates a new isolated desktop named `SecureExamDesktop` using the Windows API
   (`CreateDesktopW`). A separate desktop means other apps, notifications, and the
   taskbar are not visible to the student.
4. Launches a second copy of the app (`--secure-mode`) onto that desktop with
   `CreateProcessW`.
5. Switches the visible desktop to the secure one and **waits** for the child to
   finish.
6. In a `finally` block it **always** switches back to the original desktop and
   runs `cleanup()` — so the machine is never left locked.

It also handles both **frozen** (compiled `.exe`) and **dev** (`python -m`) modes
when deciding what command to launch.

### `run_child_process()` — what runs inside the secure desktop
1. Installs the low-level keyboard hook (only when frozen, for dev safety).
2. Starts the **Process Sentinel** (kills forbidden/screenshot apps).
3. Starts the **anti-debug background loop** in a daemon thread (one scan/minute).
4. Starts the **local login proxy** *before* Qt is initialised.
5. Configures high-DPI scaling.
6. Injects the Chromium flags directly into `sys.argv` as a guaranteed fallback
   (in case OS-level env-var inheritance fails), including the dynamic proxy
   origin and media-stream flags.
7. Creates the `QApplication`, builds the `SecureBrowser` window, and shows it
   full-screen.
8. On exit, stops the sentinel and removes the keyboard hook.

### `show_error(msg)`
Shows a native Windows message box (or prints to stderr on other platforms).

### `enforce_single_instance()`
Uses a named Windows **mutex** (`Global\SecureExamBrowser_Mutex_...`) so only one
launcher can run at a time. If the mutex already exists (error `183`), a second
launch exits silently. This prevents five rapid clicks from spawning five heavy
Chromium engines.

### `check_integrity()`
Anti-tamper checks (only meaningful for the compiled `.exe` on Windows):
- Ensures the required engine DLLs (`python3*.dll`) sit next to the executable —
  catches users who copied just the `.exe` out of the install folder.
- Refuses to run from the Windows TEMP directory — a common extraction/bypass
  trick.

### `main()` — the orchestration flow
1. `check_integrity()` — anti-tamper.
2. `probe_environment()` — one-off anti-debug / anti-VM check; aborts with a
   message if a debugger or VM is detected.
3. `enforce_single_instance()` — launcher only.
4. `_check_for_updates_blocking()` — launcher only. It calls
   `check_for_update()` and, when a newer build exists, opens
   `UpdateProgressWindow` to download an Inno Setup installer. Installation
   starts only after the user clicks the install button.
5. **Mode selection**: if `--secure-mode` → `run_child_process()`, otherwise
   → `launch_secure_desktop()`.

---

## Windows APIs used directly

Through `ctypes`, `main.py` talks to the raw Windows API:

- `user32` / `kernel32` — desktop and process management.
- `STARTUPINFO` / `PROCESS_INFORMATION` — structures required by
  `CreateProcessW` to target the new desktop.
- `CreateDesktopW`, `SwitchDesktop`, `CreateProcessW`,
  `WaitForSingleObject`, `CreateMutexW` — the low-level calls that make the
  isolated, single-instance, secure-desktop behaviour possible.

---

## In one sentence

`main.py` is the **launcher and conductor**: it verifies the environment, locks
down the PC, starts the exam browser inside an isolated desktop, and restores the
desktop and lockdown settings on its normal cleanup paths.
