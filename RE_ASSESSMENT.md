# Reverse-Engineering Resistance Assessment — TeleBrowser

**Date:** 2026-07-29
**Build analyzed:** `exe/main/` (Nuitka standalone + Cython `--harden`, extracted from the Inno Setup installer `exe/app.exe`)
**Method:** Ghidra 12.1.2 headless decompilation of all 7 Cython `.pyd` modules → static string/data analysis → per-module logic analysis by a local LLM (`gpt-oss:120b` on `dev.kmitonline.in:9879`).
**Toolchain:** `ghidra` (headless `analyzeHeadless` + custom `DecompileExport.java`), `rabin2`/`strings`/`grep`, `curl`→Ollama. Reusable driver: [`re_analyze.sh`](../re_analyze.sh).

---

## 1. Executive verdict

The `--cython --harden` build is **effective against casual/static reverse engineering but not against a determined analyst.**

- ✅ `strings`, `rabin2`, and FLOSS recover **no** config values, IPs, URLs, or key material — Cython **string compression** (`CYTHON_COMPRESS_STRINGS`) keeps them out of reach of naive tooling.
- ✅ Ghidra decompiles the modules, but the output is **semantically hollow** — pure CPython `PyObject_*` glue. There are no inline secrets and almost no readable WinAPI/crypto names to reason about.
- ⚠️ **But the protection is reversible.** The decompression routine and compressed tables ship inside the module, so an analyst can *emulate the decompression* or simply *load the `.pyd` in a controlled Python process and dump the module dict / object attributes*. Everything the obfuscation hides is recoverable **dynamically**.
- 🔴 **Strategic weakness:** the HMAC signing key is a **client-side shared secret**. No amount of client obfuscation makes a client-held secret safe — a memory dump or a one-line hook on `Fernet.__init__` / `HmacRequestInterceptor.__init__` recovers it. Obfuscation raises effort; it does not change the outcome.

**Mean static-RE resistance across modules: ~6.4 / 10 ("moderate").**

---

## 2. Per-module results

| Module | Role | Static resistance | Verdict |
|---|---|:--:|---|
| `secrets.pyd` | Fernet obfuscation of the HMAC key | **8/10** | Key not statically recoverable; needs memory dump / hook `Fernet.__init__`. |
| `process_monitor.pyd` | Forbidden-process sentinel | **7/10** | Logic in compressed bytecode; bypass by monkey-patching `ProcessSentinel` at runtime. |
| `system_locker.pyd` | Keyboard hook + Task Manager lockdown | **7/10** | Hook logic hidden; runtime-patch `toggle_task_mgr`/`hook_proc` to no-op. |
| `config.pyd` | URLs, allowlist, key, flags | **6/10** | Compression is a speed bump; run `PyInit_config` and dump the module dict to recover **all** config + secrets. |
| `login_proxy.pyd` | Reverse-proxy rewrite rules | **6/10** | Policies hidden statically; Frida/WinDbg hooks on `PyUnicode_Replace` dump proxy origins & cookies live. |
| `request_signer.pyd` | HMAC `X-Exam-*` signing | **6/10** | Key never a literal, but hook the interceptor init / HMAC call to capture key + algorithm. |
| `anti_debug.pyd` | Debugger/VM detection | **5–6/10** | Control flow visible; core heuristics in compressed bytecode. Dynamic bypass is *easy* (override `_sleep_jitter`, patch check results). |

---

## 3. Confirmed findings

### Strengths (the hardening is doing real work)
1. **Cython string compression is ON.** No IPs (`172.168.15.213`), URLs (`kmit.in`, `teleuniv`), allowlist entries, or key bytes appear via `strings`/`rabin2`.
2. **Plaintext fallback key absent.** `my_production_secret_key_12345` is **not present** anywhere in `config.pyd`/`secrets.pyd` — either removed in 1.0.1 or fully obfuscated. Good.
3. **Decompiled C is glue-only.** No inline secrets, no direct `IsDebuggerPresent`/`hmac`/`SetWindowsHookEx` names to anchor analysis on.

### Weaknesses (fix these)
1. 🔴 **Client-side shared HMAC secret.** Recoverable by dynamic analysis regardless of obfuscation. *This is the highest-impact item.*
2. 🔴 **Docstrings + qualified names leak.** `strings secrets.pyd` shows `encrypt`, `decrypt`, `_fernet`, and *"Decrypt a token produced by encrypt()…"*. Same for `SystemLocker.toggle_task_mgr`, `ProcessSentinel`, etc. This hands an attacker a map of exactly where each protection lives.
3. 🔴 **Build-path / identity leak.** `config.pyd` embeds `C:\Users\mohan\Desktop\codex\TP-browser\core/config.c` — leaks the developer username and layout.
4. 🟠 **Target IP still in the main binary.** `172.168.15.213` appears once in `SecureBrowser.exe` (Nuitka), so the exam host isn't fully hidden across the dist.
5. 🟠 **String compression is reversible.** It stops `strings`, not a controlled `.pyd` load — treat it as obfuscation, not protection.
6. 🟠 **All client-side checks are runtime-patchable.** anti-debug, process kill, keyboard lock all forward to Python objects; a DLL-injected monkey-patch defeats them. Inherent to the architecture, not a bug — but it bounds what client lockdown can guarantee.

---

## 4. Recommendations — what to do next (prioritized)

### Tier 1 — architectural (highest impact)
1. **Stop trusting the client secret.** Replace the static embedded HMAC key with **per-session, server-issued tokens** (the server hands the browser a short-lived token at exam start; the browser signs with that). Then recovering the embedded key is worthless. This neutralizes the entire `secrets`/`request_signer` attack surface.
2. **Move enforcement decisions server-side where possible.** Client lockdown (anti-debug, process kill, keyboard hook) can always be patched out at runtime; treat it as deterrence, and make the *exam server* the source of truth (e.g., server-side proctoring signals, submission validation), so a bypassed client can't silently cheat.

### Tier 2 — cheap hardening wins
3. **Strip Cython docstrings & names.** Build with `# cython: emit_code_comments=False` and compile the `.py` with docstring removal (Cython `-D`/`--no-docstrings` equivalent, or `python -OO` semantics) so `encrypt`/`decrypt`/method names stop leaking. Removes the attacker's map.
4. **Strip the build path.** Pass compiler flags to remove absolute source paths (e.g., `-ffile-prefix-map`/`-fdebug-prefix-map`, or build from a neutral dir) so `C:\Users\mohan\…` is gone.
5. **Scrub remaining plaintext infra.** Run the pre-ship grep from `PRODUCTION_DEPLOYMENT.md`; get `172.168.15.213` out of anything greppable in `SecureBrowser.exe`.

### Tier 3 — already-known items (from `DEVELOPER_REFERENCE.md §8`, still open)
6. **`certificateError()` accepts all certs** → add pinning / trusted-CA before wide rollout.
7. **Update installer unverified** → add checksum + signature to the update flow; move `UPDATE_CHECK_URL` and portals to HTTPS.
8. **`ALLOWED_DOMAINS` data bugs** → fix `"https://elms.kmce.in/download"` (should be bare host) and the dead `www.google.com` portal; make `handle_permissions` use the strict matcher.

### Tier 4 — raise the dynamic bar (optional, diminishing returns)
9. Add runtime anti-tamper (self-integrity checks, anti-injection), and consider a commercial protector (VMProtect/Themida) on `SecureBrowser.exe` **if** the threat model justifies it. Note: this only slows dynamic analysis; it never makes a client secret safe (see Tier 1).

---

## 5. Reproduce / re-run

```bash
# re-run the whole assessment on a new build's extracted dist:
./re_analyze.sh exe/main/secure_browser
```

Decompiled C and raw model responses are kept under the session scratchpad
(`scratchpad/decomp/*.c`, `scratchpad/llm/*.resp.json`). The Ghidra project
`TPBrowser` holds all 7 analyzed modules for manual inspection in the GUI.

> **Bottom line:** the obfuscation successfully stops someone from `strings`-ing
> your secrets out in five seconds, and that has real value against low-effort
> cheating. It does **not** stop a motivated analyst with a debugger. The durable
> fix is architectural — don't ship a secret the client can be tricked into
> revealing. Harden Tier 2/3 for hygiene; invest Tier 1 for actual security.
