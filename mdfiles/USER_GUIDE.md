# TeleBrowser — User Guide

**Secure Exam Browser**
For students taking an exam and for lab staff / invigilators running it.
Version: 1.0.1 · Windows only

> This guide is written in plain language. It covers how to start the browser,
> how to use it during an exam, and — most importantly — **what to do if
> something goes wrong**. You can paste this straight into Word or Google Docs.

---

## 1. What this program is

TeleBrowser is a **locked-down browser used only for online exams**. When it is
running, the computer is restricted so a student can only see the exam — other
apps, keyboard shortcuts, and switching windows are blocked. Some exams also use
the **camera** to verify the student.

While the exam browser is open:
- The screen is **full-screen** and cannot be minimized.
- Common shortcuts are blocked: the **Windows key, Alt+Tab, Alt+F4, Ctrl+Shift+Esc**, etc.
- **Task Manager is disabled.**
- Other browsers and apps (Chrome, WhatsApp, screen recorders, remote-access
  tools, etc.) are **closed automatically**.
- Right-click, F12, and Print-Screen are blocked on the exam page.

All of this turns back to normal automatically when the exam browser closes.

---

## 2. Before the exam (checklist for lab staff)

Do these **before** students sit down:

1. **Install TeleBrowser properly** using the official installer — do not just
   copy the `.exe`. It must be installed, not run from a USB or a temp folder.
2. **Connect to the exam network / Wi-Fi.** The exam servers are usually on the
   local college network.
3. **Plug in / enable the webcam** if the exam uses face verification.
4. **Close other programs** (browsers, chat apps) beforehand — the browser will
   close them anyway, but it's cleaner.
5. **Do not run it inside a virtual machine (VM)** — it will refuse to start.
6. **Do a quick test run** on one machine: open it, pick the college/portal, and
   confirm the exam page loads and the camera turns on.

---

## 3. How to start the exam browser

1. **Double-click the TeleBrowser / SecureBrowser icon** on the desktop or Start
   menu.
2. The screen switches to a secure full-screen mode. This is normal.
3. You will see the **College selection screen**.

If nothing appears after a few seconds, see **§7 "What if it breaks"**.

---

## 4. Using the browser during the exam

### 4.1 Choose your college and portal
- On the first screen, **select your college** (e.g. KMIT, NGIT, KMEC, KMCE).
- Then **choose the exam portal** (e.g. "Exam", "Test Center", "Toofan").
- The exam page loads. If the portal uses a camera, it turns on automatically —
  you do **not** need to click "Allow".

### 4.2 The toolbar (top of the screen)
| Button | What it does |
|---|---|
| **← Back** | Go back one page. On the exam's first page, it returns you to the college selection screen. |
| **Forward →** | Go forward one page. |
| **↻ Reload** | Reload the current page (use this if a page looks stuck). |
| **📶 Network** | Open the Wi-Fi manager to connect/reconnect. It shows the current Wi-Fi name. |
| **⊞ Change Portal** | Go back to pick a different college/portal. |
| **Exit Session** | Close the exam browser (asks for confirmation first). |

### 4.3 Connecting to Wi-Fi
1. Click **📶 Network**.
2. Click **🔄 Refresh** to scan.
3. Pick your network:
   - **Saved networks** show "Saved (tap Connect)" — just click **🔗 Connect**.
   - **New networks** ask for the password.
4. On success the exam page reloads automatically.

### 4.4 Finishing / leaving the exam
- Click **Exit Session** and confirm.
- The computer returns to normal (Task Manager, shortcuts, and other apps work
  again).

---

## 5. The camera (for face-verification exams)

- The camera turns on **by itself** on portals that need it — no pop-up to allow.
- If the camera does **not** turn on, see **§7**. The usual causes are: the
  webcam is unplugged/disabled, another app is using it, or a network issue.

---

## 6. Important "do nots" during an exam

- **Do not** try to open other apps or switch windows — they are blocked and may
  close the exam.
- **Do not** run the browser inside a virtual machine or with a debugger — it
  will shut down with a security message.
- **Do not** unplug the webcam mid-exam if the exam uses face verification.
- **Do not** force-shut the computer unless told to — use **Exit Session**.

---

## 7. What if it breaks? (Troubleshooting)

Work top to bottom. Most problems are **network/Wi-Fi**, not the exam itself.

### 7.1 The browser won't open / nothing happens
- **Wait 10–15 seconds** — it can be slow to start the first time.
- **Try again** — double-click the icon once more.
- **Restart the computer** and open it again.
- **Make sure it was installed properly** (not copied to a USB/temp folder). If
  it was copied, reinstall using the official installer.
- If it shows **"Integrity Check Failed"** → the files were moved or are
  incomplete. **Reinstall** the browser.
- If it shows **"another instance is already running"** or just closes → it may
  already be open. Restart the PC and try once.

### 7.2 "Security Breach / cannot run in this environment"
The browser detected a **virtual machine or a debugger**.
- **Close** any VM software (VirtualBox, VMware, Docker/WSL) and developer tools.
- If this is a **normal physical PC** and it still complains, note the exact
  message and tell the lab in-charge / developer — the machine may have VM-related
  software installed that needs removing.

### 7.3 The exam page won't load / "Can't reach the exam server"
This is almost always a **network problem, not the exam**.
- Click **📶 Network** and check you're on the **correct exam Wi-Fi**.
- Click **↻ Reload**.
- Click **↻ Try Again** on the error page.
- Ask the invigilator whether the **exam server is up** and whether you're on the
  right network.
- Try moving to a spot with a stronger Wi-Fi signal.

### 7.4 "Check your connection" full-screen message
Same as above — a network drop.
- Reconnect via **📶 Network**, then **↻ Try Again**.

### 7.5 Blank page or "site blocked"
- Use **⊞ Change Portal** and make sure you picked the **correct portal** for your
  college.
- If a specific portal always shows this, the portal's address may be misconfigured
  — tell the lab in-charge (it needs a settings fix by the developer).

### 7.6 Camera not working
- Check the **webcam is plugged in and enabled** (not covered, not disabled in
  BIOS/Device Manager).
- **Close any other app** that might be using the camera (Zoom, Teams, Camera app)
  — but note those get closed automatically anyway.
- Click **↻ Reload** to reload the exam page.
- Confirm you selected a portal that actually **uses** the camera.
- If it still fails, tell the invigilator — it may be a settings issue for that
  portal.

### 7.7 The screen looks frozen / stuck
- Click **↻ Reload**.
- Wait a few seconds — a slow network can look like a freeze.
- If truly stuck, use **Exit Session** and reopen. (Your exam progress is saved on
  the server for most portals, but check with the invigilator first.)

### 7.8 The app closed by itself
- Reopen it and continue — most portals save progress on the server.
- If it keeps closing, it may be detecting a **blocked app** (another browser,
  screen recorder, remote tool). Make sure those are fully closed, then reopen.
- Tell the invigilator so they can note it.

### 7.9 Keyboard shortcuts / Task Manager not working
- **This is intentional** while the exam is running — the Windows key, Alt+Tab,
  Task Manager, etc. are blocked on purpose.
- They return to normal **after you Exit Session**.

### 7.10 After a crash, Task Manager / shortcuts are STILL blocked
Rare — happens only if the app closed abnormally.
- **Restart the computer** — that restores everything.
- If it persists after a restart, lab staff can re-enable Task Manager:
  set the registry value
  `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Policies\System\DisableTaskMgr`
  to `0` (or delete it), then restart.

### 7.11 College logo missing on the selection screen
- Cosmetic only — it does not affect the exam. You can still select and continue.
- Report it to lab staff; the logo file may be missing from the install.

### 7.12 Wi-Fi won't connect from inside the browser
- Double-check the **password**.
- Click **🔄 Refresh** and try again.
- Some saved-network features need admin rights; if it won't connect, connect to
  Wi-Fi **before** launching, then reopen the browser.

---

## 8. Quick reference — who fixes what

| Situation | Student can | Invigilator / lab staff |
|---|---|---|
| Won't load / network error | Reconnect Wi-Fi, Reload, Try Again | Check exam server + network |
| Won't open / Integrity error | Restart PC | Reinstall properly |
| Security / VM message | — | Remove VM software; escalate |
| Camera off | Check webcam, Reload | Check portal settings |
| Stuck after crash | Restart PC | Re-enable Task Manager if needed |
| Wrong/blocked portal | Change Portal | Fix config; escalate to developer |

---

## 9. Golden rules

1. **Most failures are Wi-Fi.** Check the network first, always.
2. **Reload → Try Again → Reconnect Wi-Fi → Restart PC** — in that order.
3. **Use Exit Session** to leave; don't force-shutdown.
4. **When in doubt, tell the invigilator** and note the exact on-screen message —
   it makes fixing it much faster.

---

*If a problem isn't covered here, note the exact message shown on screen and the
portal you were on, and report it to the lab in-charge or the TeleBrowser
developer.*
