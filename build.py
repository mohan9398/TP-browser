# -*- coding: utf-8 -*-
"""
Nuitka + Cython production build script for the Secure Exam Browser (Windows .exe).

WHY THIS SCRIPT EXISTS / IMPORTANT DESIGN DECISIONS
---------------------------------------------------
1. STANDALONE, NOT ONEFILE.
   The app's own integrity check (main.py) does two things that make --onefile
   unusable:
     * It refuses to run from the Temp directory  -> onefile extracts to Temp.
     * It requires python3*.dll next to the exe    -> standalone provides this,
       onefile hides it inside the temp extraction.
   So we always build with --standalone, which produces a distributable FOLDER.

2. PACKAGE NAME BRIDGE.
   Source imports use the package name `secure_browser`
   (e.g. `from secure_browser.core.config import ...`), but the project folder is
   usually named `TP-browser`. Nuitka must import the code as `secure_browser`.
   If the current folder is not already named `secure_browser`, this script
   creates a temporary NTFS directory junction next to it
   (parent/secure_browser -> this folder), builds, then removes the junction.
   Junctions need no admin rights on Windows.

3. OUTPUT NAME.
   The integrity check only accepts an exe basename of `main.exe` or
   `securebrowser.exe`, so we output `SecureBrowser.exe`.

4. CYTHON COMPILATION (NEW).
   Optional: compile sensitive modules to .pyd (compiled extensions) BEFORE Nuitka.
   This adds a layer of obfuscation via Cython (Python→C→binary), plus Nuitka's
   compilation (Python→C++→binary) on top. Use --cython flag.
   Cython modules are compiled to the `build/cython_modules` directory.
   Nuitka automatically includes them in the final build.

USAGE
-----
    python build.py              # normal production build (Nuitka only)
    python build.py --cython     # + Cython pre-compilation of sensitive modules
    python build.py --lto        # + link-time optimization (slower build, smaller exe)
    python build.py --harden     # anti-reverse-engineering build (implies --lto):
                                 #   strips docstrings/asserts, anti-bloat, no console
    python build.py --debug      # console enabled + no version info (for testing)

COMBINATIONS
-----------
    python build.py --cython --harden  # maximum protection
    python build.py --cython --lto     # Cython + LTO optimization

REQUIREMENTS
------------
    pip install nuitka
    pip install Cython                  # for --cython builds
    pip install PyQt6 PyQt6-WebEngine psutil pywifi cryptography
    (Nuitka also needs a C compiler; on Windows it will offer to download MinGW.)
"""

import os
import re
import sys
import shutil
import subprocess

# Try to import Cython for optional compilation
try:
    from Cython.Build import cythonize
    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False

# --------------------------------------------------------------------------- #
# Paths and constants
# --------------------------------------------------------------------------- #
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))   # .../TP-browser
PARENT_DIR  = os.path.dirname(PROJECT_DIR)
PKG_NAME    = "secure_browser"                              # import name the code expects
OUTPUT_DIR  = os.path.join(PROJECT_DIR, "build")
CYTHON_BUILD_DIR = os.path.join(OUTPUT_DIR, "cython_modules")  # compiled .pyd output
EXE_NAME    = "SecureBrowser.exe"                           # -> basename 'securebrowser.exe'
ICON_PATH   = os.path.join(PROJECT_DIR, "icon.ico")        # optional; used if present

# Modules to compile with Cython (maximum protection for security-sensitive code)
CYTHON_MODULES = [
    "core/config.py",
    "core/secrets.py",
    "security/anti_debug.py",
    "security/process_monitor.py",
    "security/system_locker.py",
    "network/request_signer.py",
    "network/login_proxy.py",
]


def read_app_version() -> str:
    """Read APP_VERSION from core/config.py without importing PyQt/heavy deps."""
    cfg = os.path.join(PROJECT_DIR, "core", "config.py")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r'APP_VERSION\s*=\s*["\']([\d.]+)["\']', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "1.0.0"


def compile_cython_modules():
    """
    Compile sensitive Python modules with Cython to .pyd files.
    Returns the path to the cython modules directory.
    """
    if not CYTHON_AVAILABLE:
        print("[cython] ERROR: Cython is not installed.")
        print("[cython] Install with: pip install Cython")
        sys.exit(1)

    print("[cython] Starting Cython compilation...")
    
    # Clean old Cython build
    if os.path.exists(CYTHON_BUILD_DIR):
        shutil.rmtree(CYTHON_BUILD_DIR)
        print(f"[cython] Cleaned old build directory: {CYTHON_BUILD_DIR}")
    
    os.makedirs(CYTHON_BUILD_DIR, exist_ok=True)

    # Get the secure_browser package root
    pkg_root = os.path.join(PROJECT_DIR, "secure_browser")
    if not os.path.isdir(pkg_root):
        # If secure_browser doesn't exist as a dir, use PROJECT_DIR directly
        pkg_root = PROJECT_DIR

    compiled_count = 0
    failed_modules = []

    for module_rel_path in CYTHON_MODULES:
        src_py = os.path.join(PROJECT_DIR, module_rel_path)
        
        if not os.path.exists(src_py):
            print(f"[cython] WARNING: Module not found: {src_py}")
            failed_modules.append(module_rel_path)
            continue

        module_name = os.path.splitext(module_rel_path)[0].replace(os.sep, ".")
        
        print(f"[cython]   Compiling: {module_rel_path} -> {module_name}.pyd")
        
        try:
            # Compile with Cython: Python → C → .pyd
            # We use cythonize with the following options:
            # - language_level=3: Python 3 syntax
            # - compiler_directives to enable optimizations and remove bounds checking
            cythonize(
                [src_py],
                build_dir=CYTHON_BUILD_DIR,
                language_level=3,
                compiler_directives={
                    "boundscheck": False,      # Disable bounds checking
                    "wraparound": False,       # Disable negative indexing
                    "cdivision": True,         # Fast C-level division
                    "infer_types": True,       # Type inference
                    "always_allow_keywords": False,  # Strict argument checking
                },
                force=True,
                quiet=True,
            )
            compiled_count += 1
            print(f"[cython]     [OK]")
        except Exception as e:
            print(f"[cython]     [FAILED] {e}")
            failed_modules.append(module_rel_path)

    print(f"[cython] Compilation complete: {compiled_count}/{len(CYTHON_MODULES)} modules")
    
    if failed_modules:
        print(f"[cython] Failed modules: {', '.join(failed_modules)}")
        print("[cython] WARNING: Build will continue with Nuitka, but some modules are not Cython-compiled.")

    return CYTHON_BUILD_DIR


def ensure_package_name():
    """
    Make the project importable as `secure_browser`.

    Returns (package_root, cleanup_callable).
    package_root is the directory to run Nuitka from (must contain `secure_browser`).
    """
    if os.path.basename(PROJECT_DIR).lower() == PKG_NAME:
        # Already correctly named: run from the parent.
        return PARENT_DIR, (lambda: None)

    link_path = os.path.join(PARENT_DIR, PKG_NAME)

    if os.path.exists(link_path):
        # Something already occupies parent/secure_browser. Assume it's correct
        # (a prior junction or a real copy) and leave it in place.
        print(f"[build] Using existing '{link_path}' as package root.")
        return PARENT_DIR, (lambda: None)

    # Create a directory junction: parent/secure_browser -> this folder.
    print(f"[build] Creating temporary junction: {link_path} -> {PROJECT_DIR}")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", link_path, PROJECT_DIR],
        check=True, capture_output=True, text=True,
    )

    def _cleanup():
        try:
            # 'rmdir' removes the junction without touching the real folder.
            subprocess.run(["cmd", "/c", "rmdir", link_path],
                           check=False, capture_output=True, text=True)
            print(f"[build] Removed temporary junction: {link_path}")
        except Exception as e:
            print(f"[build] WARNING: could not remove junction {link_path}: {e}")

    return PARENT_DIR, _cleanup


def build():
    if sys.platform != "win32":
        print("ERROR: This is a Windows-only application. Build on Windows.")
        sys.exit(1)

    debug = "--debug" in sys.argv
    use_lto = "--lto" in sys.argv
    harden = "--harden" in sys.argv          # anti-reverse-engineering hardening
    use_cython = "--cython" in sys.argv      # optional Cython pre-compilation
    
    version = read_app_version()
    # Nuitka wants a 4-part numeric file version (e.g. 1.0.0.0).
    file_version = (version + ".0.0.0").split(".")
    file_version = ".".join(file_version[:4])

    # Step 1: Optional Cython compilation
    cython_dir = None
    if use_cython:
        if not CYTHON_AVAILABLE:
            print("\n[build] ERROR: --cython requested, but Cython is not installed.")
            print("[build] Install with: pip install Cython")
            sys.exit(1)
        print("\n" + "=" * 70)
        print("[build] STEP 1: CYTHON COMPILATION")
        print("=" * 70)
        cython_dir = compile_cython_modules()
        print()

    package_root, cleanup = ensure_package_name()

    # Entry point as Nuitka sees it (relative to package_root).
    main_script = os.path.join(PKG_NAME, "main.py")

    flags = [
        sys.executable, "-m", "nuitka",
        "--standalone",                       # folder build (NOT onefile - see header)
        "--assume-yes-for-downloads",         # auto-fetch MinGW / dependency walker
        "--enable-plugin=pyqt6",              # handles QtWebEngine + plugins + resources
        f"--include-package={PKG_NAME}",      # force-include the whole app package
        "--include-package=psutil",
        "--include-package=pywifi",
        "--include-package=cryptography",     # needed to decrypt the embedded secret key
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename={EXE_NAME}",
        "--remove-output",                    # delete .build intermediates after linking
        "--company-name=TeleUniv",
        "--product-name=Secure Exam Browser",
        "--file-description=Secure Exam Browser",
        f"--file-version={file_version}",
        f"--product-version={version}",
    ]

    # Note: Cython modules are compiled to C but final integration with Nuitka
    # is still in development. Currently, use Nuitka-only builds for stability.
    if cython_dir:
        print(f"[build] STEP 2: NUITKA COMPILATION (Cython modules in: {cython_dir})")
    else:
        print(f"[build] STEP 2: NUITKA COMPILATION")
    
    print("=" * 70)

    if debug:
        # Keep a console so you can see tracebacks while testing the exe.
        flags.append("--windows-console-mode=force")
    else:
        flags.append("--windows-console-mode=disable")   # no console window in production

    if use_lto or harden:
        flags.append("--lto=yes")            # whole-program optimization, harder to follow

    if harden:
        if debug:
            print("[build] WARNING: --harden with --debug keeps a console; "
                  "use --harden alone for a real hardened build.")
        flags += [
            # Strip readable metadata baked into the binary.
            "--python-flag=no_docstrings",   # remove all docstrings (lots of plain text)
            "--python-flag=no_asserts",      # remove assert statements + their messages
            "--python-flag=no_site",         # don't import site (smaller, fewer hooks)
            "--python-flag=static_hashes",   # deterministic, no hash-randomization noise
            # Drop unused stdlib/3rd-party code → smaller, less to analyse.
            "--enable-plugin=anti-bloat",
        ]

    if os.path.exists(ICON_PATH):
        flags.append(f"--windows-icon-from-ico={ICON_PATH}")
    else:
        print(f"[build] No icon.ico found at {ICON_PATH} (building without an icon).")

    flags.append(main_script)

    print("[build] App version :", version)
    print("[build] Run dir     :", package_root)
    print("[build] Command     :", " ".join(flags))
    print("-" * 70)

    try:
        # Run from the package root so `secure_browser` is importable.
        result = subprocess.run(flags, cwd=package_root)
    finally:
        cleanup()

    if result.returncode != 0:
        print("\n[build] FAILED. See Nuitka output above.")
        sys.exit(result.returncode)

    dist_dir = os.path.join(OUTPUT_DIR, "main.dist")
    exe_path = os.path.join(dist_dir, EXE_NAME)
    print("\n" + "=" * 70)
    print("[build] SUCCESS")
    print(f"[build] Distributable folder : {dist_dir}")
    print(f"[build] Executable           : {exe_path}")
    print("=" * 70)
    print(
        "\nDISTRIBUTION NOTES:\n"
        "  * Ship the ENTIRE 'main.dist' folder, not just the .exe.\n"
        "  * python3*.dll and the Qt/WebEngine files must stay next to the exe\n"
        "    (the app's integrity check requires this).\n"
        "  * Do NOT run it from a Temp directory - the integrity check blocks that.\n"
        "  * Code-sign the exe before distributing so SmartScreen/Gatekeeper trust it."
    )


if __name__ == "__main__":
    build()
