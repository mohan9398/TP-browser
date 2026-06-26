# TP-Browser Build Guide: Nuitka + Cython Protection

This guide explains how to build your application with **Nuitka** (Python → C++ → binary) and optionally **Cython** (Python → C → binary) for maximum code protection against reverse engineering.

## Overview

### What Each Tool Does

| Tool    | Process | Output | Protection Level |
|---------|---------|--------|------------------|
| **Nuitka** | Python → C++ → Machine Code | `.exe` + dependencies | High (whole app compiled) |
| **Cython** | Python → C → Compiled Extensions | `.pyd` files | High (module-level) |
| **Both** | Nuitka + Cython modules | `.exe` + `.pyd` + dependencies | **Maximum** (layered protection) |

### When to Use Each

- **Nuitka only** (`python build.py`): Fast builds, sufficient protection for most cases
- **Nuitka + LTO** (`python build.py --lto`): Slower build, smaller exe, better optimization
- **Nuitka + Cython** (`python build.py --cython`): Extra obfuscation for security-sensitive modules
- **Maximum hardening** (`python build.py --cython --harden`): All protections enabled (slowest build)

## Prerequisites

### 1. Install Build Dependencies

```powershell
pip install -r requirements-build.txt
```

Or manually:

```powershell
pip install nuitka Cython PyQt6 PyQt6-WebEngine psutil pywifi cryptography
```

### 2. C/C++ Compiler

Nuitka requires a C++ compiler. On Windows:

- **Option A (Automatic)**: Run `python build.py` and accept the MinGW download prompt
- **Option B (Manual)**: Install Visual Studio Build Tools or MinGW-w64

## Build Modes

### Mode 1: Basic Nuitka Build (Recommended for most users)

```powershell
python build.py
```

**Output**: `build/main.dist/SecureBrowser.exe` + supporting files

**Build time**: ~5-15 minutes

**Features**:
- Full Python → C++ compilation
- Removes docstrings and optimizes code
- Hardened against basic reverse engineering

### Mode 2: Nuitka + Cython (Extra Protection)

```powershell
python build.py --cython
```

**What it does**:
1. Compiles security-sensitive modules with Cython:
   - `core/config.py` → `config.pyd`
   - `core/secrets.py` → `secrets.pyd`
   - `security/anti_debug.py` → `anti_debug.pyd`
   - `security/process_monitor.py` → `process_monitor.pyd`
   - `security/system_locker.py` → `system_locker.pyd`
   - `network/request_signer.py` → `request_signer.pyd`
   - `network/login_proxy.py` → `login_proxy.pyd`

2. Nuitka then compiles the remaining code + includes the `.pyd` files

**Output**: `build/main.dist/SecureBrowser.exe` + Cython `.pyd` modules + dependencies

**Build time**: ~15-30 minutes (Cython adds 5-15 minutes)

**Protection**: Maximum obfuscation (modules compiled twice in different ways)

### Mode 3: Link-Time Optimization

```powershell
python build.py --lto
```

**Build time**: ~15-30 minutes (LTO adds significant time)

**Features**:
- Whole-program optimization
- Smaller executable
- Harder to analyze

### Mode 4: Hardened Build (Anti-Reverse-Engineering)

```powershell
python build.py --harden
```

**Build time**: ~20-40 minutes

**Features** (implies `--lto`):
- Removes all docstrings from the binary
- Removes assert statements
- Enables anti-bloat (removes unused stdlib code)
- No console window (production-ready)
- Static hash randomization

### Mode 5: Maximum Protection

```powershell
python build.py --cython --harden
```

**The nuclear option**: All protections enabled

**Build time**: ~40-60 minutes

**Protection**: Maximum (4 layers):
1. Cython compilation (Python → C)
2. Nuitka compilation (Python → C++)
3. LTO optimization
4. Anti-bloat + docstring/assert removal

## Advanced: Customizing Cython Modules

Edit `build.py` and modify the `CYTHON_MODULES` list:

```python
CYTHON_MODULES = [
    "core/config.py",
    "core/secrets.py",
    "security/anti_debug.py",
    "security/process_monitor.py",
    "security/system_locker.py",
    "network/request_signer.py",
    "network/login_proxy.py",
    # Add more modules here for extra protection
]
```

**Note**: Compile speed increases with more modules. Start with security-sensitive ones.

## Debugging Build Issues

### Issue: "Cython is not installed"

```powershell
pip install Cython
```

### Issue: "C compiler not found"

Nuitka will offer to download MinGW. Accept the prompt, or:

```powershell
pip install mingw-w64
```

### Issue: Build fails with "cannot find module"

Ensure all dependencies are installed:

```powershell
pip install PyQt6 PyQt6-WebEngine psutil pywifi cryptography
```

### Issue: Cython modules fail to compile

Check that the module paths in `CYTHON_MODULES` are correct relative to `PROJECT_DIR`.

## Distribution

After a successful build:

1. **Entire folder**: Ship the complete `build/main.dist/` folder
   - `.exe` file
   - All `.dll` files (Python runtime, Qt, WebEngine)
   - All `.pyd` files (including Cython-compiled modules)
   - All resource files (translations, plugins)

2. **Do NOT ship**:
   - The `build/` or `build/.build` directories
   - Source `.py` files
   - The junction directory (if created)

3. **Important**: The integrity check in `main.py` requires:
   - Python runtime DLLs next to the exe
   - No execution from Temp directory
   - Code signing recommended (SmartScreen/Gatekeeper)

## Performance Impact

| Build Mode | Build Time | Exe Size | Runtime Speed | Reverse Eng. Difficulty |
|-----------|-----------|----------|---------------|----------------------|
| Nuitka only | ~5-10m | ~200MB | Fast | Medium |
| Nuitka + LTO | ~15-30m | ~150MB | Fast | High |
| Nuitka + Cython | ~15-30m | ~220MB | Fast | Very High |
| Max (Cython + Harden) | ~40-60m | ~120MB | Fast | Extremely High |

## What Gets Compiled vs. What Doesn't

### Always Compiled (with Nuitka)
- `main.py` and all imports
- Standard library used by your app
- Third-party libraries (PyQt6, cryptography, etc.)

### Additionally Compiled (with `--cython`)
- Modules listed in `CYTHON_MODULES`
- Becomes `.pyd` (binary extensions)
- Cannot be directly imported as `.py` anymore

### Not Compiled
- The app still needs Python runtime DLLs
- Config files, resources, translations
- Non-code data files

## Tips for Maximum Protection

1. **Always use `--harden`** for production builds
   - Removes readable strings (docstrings, assert messages)
   - Reduces binary size by 30-50%

2. **Use `--cython`** for security-critical code
   - Adds a second layer of obfuscation
   - Modules in `CYTHON_MODULES` are hardest to reverse-engineer

3. **Code sign the executable**
   - Prevents SmartScreen warnings
   - Shows legitimate Windows application

4. **Keep source code private**
   - Only distribute the compiled `.exe`
   - Never distribute `.py` files with the binary

5. **Monitor for unpacking attempts**
   - Your `anti_debug.py` helps detect debuggers
   - Consider adding telemetry for detection

## Troubleshooting Performance

If the build is too slow:

1. Remove unnecessary modules from `CYTHON_MODULES`
   - Start with only `core/secrets.py`, `security/anti_debug.py`
   
2. Use only `--lto` instead of `--harden` for faster builds
   
3. Skip Cython entirely if build time is critical:
   ```powershell
   python build.py --harden  # No Cython, still very protected
   ```

## Further Reading

- [Nuitka Documentation](https://nuitka.net/)
- [Cython Documentation](https://cython.readthedocs.io/)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
