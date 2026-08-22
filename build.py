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

4. CYTHON + NUITKA DOUBLE COMPILATION (--cython flag).
   Pipeline:
     a) Cython compiles sensitive .py files → .c (C source)
     b) C compiler (MSVC / MinGW) compiles .c → .pyd (binary extension module)
        The .pyd files are placed IN-PLACE next to the original .py files.
     c) Nuitka runs on the package. Python's import system prefers .pyd over .py,
        so Nuitka picks up the pre-compiled binaries and copies them into main.dist.
     d) After the Nuitka build finishes, all generated .pyd and .c files are
        removed from the source tree, restoring it to its original state.
   Result: sensitive modules exist only as binary blobs (not Python bytecode)
   inside main.dist, making them very hard to reverse-engineer.

USAGE
-----
    python build.py              # Nuitka only
    python build.py --cython     # Cython .pyd pre-compilation + Nuitka (recommended)
    python build.py --lto        # + link-time optimization (slower build, smaller exe)
    python build.py --harden     # strip docstrings/asserts, anti-bloat (implies --lto)
    python build.py --debug      # console enabled + no version info (for testing)

BEST PROTECTION
---------------
    python build.py --cython --harden

REQUIREMENTS
------------
    pip install nuitka Cython PyQt6 PyQt6-WebEngine psutil pywifi cryptography
    (Nuitka needs a C compiler; on Windows it will offer to download MinGW.)
"""

import glob
import os
import re
import sys
import shutil
import subprocess

try:
    from Cython.Build import cythonize
    CYTHON_AVAILABLE = True
except ImportError:
    CYTHON_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Paths and constants
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_DIR      = os.path.abspath(os.path.dirname(__file__))
PARENT_DIR       = os.path.dirname(PROJECT_DIR)
PKG_NAME         = "secure_browser"
OUTPUT_DIR       = os.path.join(PROJECT_DIR, "build")
CYTHON_TEMP_DIR  = os.path.join(OUTPUT_DIR, "cython_tmp")   # C compiler temp files
EXE_NAME         = "SecureBrowser.exe"
ICON_PATH        = os.path.join(PROJECT_DIR, "Browser.ico")

# Sensitive modules compiled with Cython → .pyd before Nuitka runs.
# These are the modules that contain security logic, secrets, and signing code.
CYTHON_MODULES = [
    "core/config.py",
    "core/codec.py",
    "security/envprobe.py",
    "security/watchdog.py",
    "security/wsession.py",
    "network/netheaders.py",
    "network/localgw.py",
]


# ─────────────────────────────────────────────────────────────────────────────

def read_app_version() -> str:
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
    Full Cython pipeline: .py → .c (Cython) → .pyd (C compiler), in-place.

    Each .pyd is placed next to its source .py file so that Python's import
    system (and therefore Nuitka) automatically prefers the binary over the
    source.

    Returns (pyd_files, c_files) — lists of generated file paths to clean up
    after the Nuitka build.
    """
    if not CYTHON_AVAILABLE:
        print("[cython] ERROR: Cython is not installed. Run: pip install Cython")
        sys.exit(1)

    os.makedirs(CYTHON_TEMP_DIR, exist_ok=True)

    print("[cython] Step 1 of 2: Compiling sensitive modules  (.py → .c → .pyd)")
    print("-" * 70)

    generated_pyds = []
    generated_c    = []
    failed         = []

    for module_rel in CYTHON_MODULES:
        src_py   = os.path.join(PROJECT_DIR, module_rel)
        src_dir  = os.path.dirname(src_py)
        basename = os.path.splitext(os.path.basename(module_rel))[0]

        if not os.path.exists(src_py):
            print(f"  SKIP  {module_rel}  (file not found)")
            continue

        print(f"  {module_rel}", end="  ...", flush=True)

        # Write a minimal in-memory setup script to a temp file.
        # We cannot use -c because setuptools parses sys.argv for its own flags.
        setup_script = os.path.join(src_dir, "_cython_setup_tmp.py")
        setup_code = (
            "from setuptools import setup, Extension\n"
            "from Cython.Build import cythonize\n"
            # Tier 1 hardening: strip docstrings from the compiled module so
            # `strings <module>.pyd` no longer reveals things like
            # encrypt/decrypt/"Decrypt a token produced by encrypt()..." — i.e.
            # remove the map that tells an analyst where each protection lives.
            "from Cython.Compiler import Options\n"
            "Options.docstrings = False\n"
            "setup(\n"
            "    ext_modules=cythonize(\n"
            # Pass a RELATIVE source name (cwd is already the module's dir). Using
            # the absolute path here embedded C:\\Users\\<name>\\...\\config.c into
            # the .pyd, leaking the developer username and project layout.
            f"        [Extension('{basename}', [r'{basename}.py'])],\n"
            "        language_level=3,\n"
            "        compiler_directives={\n"
            "            'boundscheck': False,\n"
            "            'wraparound': False,\n"
            "            'cdivision': True,\n"
            "            'infer_types': True,\n"
            "        },\n"
            "        force=True,\n"
            "    )\n"
            ")\n"
        )
        with open(setup_script, "w", encoding="utf-8") as f:
            f.write(setup_code)

        try:
            result = subprocess.run(
                [
                    sys.executable, setup_script,
                    "build_ext", "--inplace",
                    f"--build-temp={CYTHON_TEMP_DIR}",
                ],
                cwd=src_dir,
                capture_output=True,
                text=True,
            )

            # Track the generated .c file for cleanup
            c_file = os.path.join(src_dir, f"{basename}.c")
            if os.path.exists(c_file):
                generated_c.append(c_file)

            if result.returncode == 0:
                # Find the produced .pyd (e.g. config.cpython-313-win_amd64.pyd)
                pyd_matches = glob.glob(os.path.join(src_dir, f"{basename}*.pyd"))
                if pyd_matches:
                    generated_pyds.extend(pyd_matches)
                    print(f"  OK  →  {os.path.basename(pyd_matches[0])}")
                else:
                    print("  WARN — build succeeded but no .pyd found")
                    failed.append(module_rel)
            else:
                print(f"  FAILED")
                # Show last 3 lines of stderr for diagnosis
                err_lines = [l for l in result.stderr.splitlines() if l.strip()]
                for line in err_lines[-3:]:
                    print(f"    {line}")
                failed.append(module_rel)

        except Exception as exc:
            print(f"  ERROR: {exc}")
            failed.append(module_rel)

        finally:
            if os.path.exists(setup_script):
                os.remove(setup_script)

    ok_count = len(generated_pyds)
    print("-" * 70)
    print(f"[cython] {ok_count}/{len(CYTHON_MODULES)} modules compiled to .pyd")

    if failed:
        print(f"[cython] Failed: {', '.join(failed)}")
        print("[cython] Build will continue — Nuitka will compile those from source.")
    else:
        print("[cython] All sensitive modules are now binary-only .pyd files.")

    print()
    return generated_pyds, generated_c


def _cleanup_cython_artifacts(pyd_files, c_files):
    """Remove .pyd and .c files that were placed in-source for the build."""
    removed = 0
    for f in pyd_files + c_files:
        try:
            os.remove(f)
            removed += 1
        except Exception:
            pass
    # Remove the C compiler temp dir
    if os.path.exists(CYTHON_TEMP_DIR):
        shutil.rmtree(CYTHON_TEMP_DIR, ignore_errors=True)
    if removed:
        print(f"[cython] Cleaned {removed} generated file(s) from source tree.")


def ensure_package_name():
    """
    Make the project importable as `secure_browser`.
    Returns (package_root, cleanup_callable).
    """
    if os.path.basename(PROJECT_DIR).lower() == PKG_NAME:
        return PARENT_DIR, (lambda: None)

    link_path = os.path.join(PARENT_DIR, PKG_NAME)

    if os.path.exists(link_path):
        print(f"[build] Using existing '{link_path}' as package root.")
        return PARENT_DIR, (lambda: None)

    print(f"[build] Creating temporary junction: {link_path} → {PROJECT_DIR}")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", link_path, PROJECT_DIR],
        check=True, capture_output=True, text=True,
    )

    def _cleanup():
        try:
            subprocess.run(
                ["cmd", "/c", "rmdir", link_path],
                check=False, capture_output=True, text=True,
            )
            print(f"[build] Removed temporary junction: {link_path}")
        except Exception as exc:
            print(f"[build] WARNING: could not remove junction {link_path}: {exc}")

    return PARENT_DIR, _cleanup


def purge_stale_artifacts():
    """Remove any Cython .pyd/.c left next to the source modules.

    A previous build that was interrupted (Ctrl+C) skips its cleanup and leaves
    compiled .pyd files in the source tree. Python then imports those .pyd over
    the .py — which also makes the anti-tamper guard in codec.py fire during
    normal `python` runs. Wipe them before every build so the tree is always
    clean going in.
    """
    removed = 0
    for module_rel in CYTHON_MODULES:
        src_dir  = os.path.dirname(os.path.join(PROJECT_DIR, module_rel))
        basename = os.path.splitext(os.path.basename(module_rel))[0]
        for pattern in (f"{basename}*.pyd", f"{basename}.c"):
            for path in glob.glob(os.path.join(src_dir, pattern)):
                try:
                    os.remove(path)
                    removed += 1
                except Exception:
                    pass
    if removed:
        print(f"[build] Pre-clean: removed {removed} stale Cython artifact(s) from source.")


def build():
    if sys.platform != "win32":
        print("ERROR: This is a Windows-only application.")
        sys.exit(1)

    debug     = "--debug"   in sys.argv
    use_lto   = "--lto"     in sys.argv
    harden    = "--harden"  in sys.argv
    use_cython = "--cython" in sys.argv

    version = read_app_version()
    file_version = ".".join((version + ".0.0.0").split(".")[:4])

    # Always start from a clean source tree (guards against an interrupted
    # previous build leaving .pyd files behind).
    purge_stale_artifacts()

    # ── Step 1: Cython ────────────────────────────────────────────────────────
    pyd_files, c_files = [], []
    if use_cython:
        print("\n" + "=" * 70)
        print("[build] STEP 1 — CYTHON: .py → .pyd  (binary extension modules)")
        print("=" * 70)
        pyd_files, c_files = compile_cython_modules()

    # ── Step 2: Nuitka ────────────────────────────────────────────────────────
    package_root, junction_cleanup = ensure_package_name()
    main_script = os.path.join(PKG_NAME, "main.py")

    step_label = "STEP 2" if use_cython else "STEP 1"
    print(f"\n{'=' * 70}")
    print(f"[build] {step_label} — NUITKA: package → standalone exe")
    if pyd_files:
        print(f"[build]   {len(pyd_files)} Cython .pyd file(s) will be bundled as-is (binary).")
        print(f"[build]   Remaining modules compiled by Nuitka (Python → C++).")
    print("=" * 70)

    flags = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyqt6",
        f"--include-package={PKG_NAME}",
        "--include-package=psutil",
        "--include-package=pywifi",
        "--include-package=cryptography",
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename={EXE_NAME}",
        "--remove-output",
        "--company-name=TeleUniv",
        "--product-name=Secure Exam Browser",
        "--file-description=Secure Exam Browser",
        f"--file-version={file_version}",
        f"--product-version={version}",
    ]

    flags.append("--windows-console-mode=force" if debug else "--windows-console-mode=disable")

    if use_lto or harden:
        flags.append("--lto=yes")

    if harden:
        if debug:
            print("[build] WARNING: --harden with --debug keeps a console.")
        flags += [
            "--python-flag=no_docstrings",
            "--python-flag=no_asserts",
            "--python-flag=no_site",
            "--python-flag=static_hashes",
            "--enable-plugin=anti-bloat",
        ]

    # College logos — the selector loads these from images/ next to the exe.
    images_dir = os.path.join(PROJECT_DIR, "images")
    if os.path.isdir(images_dir):
        flags.append(f"--include-data-dir={images_dir}=images")
    else:
        print(f"[build] WARNING: no images/ dir at {images_dir} — college logos will be missing.")

    if os.path.exists(ICON_PATH):
        flags.append(f"--windows-icon-from-ico={ICON_PATH}")
    else:
        print(f"[build] No icon found at {ICON_PATH} — building without icon.")

    flags.append(main_script)

    lto_on = use_lto or harden
    est = "20-40 min" if lto_on else "5-15 min"
    print(f"[build] Version     : {version}")
    print(f"[build] Run dir     : {package_root}")
    print(f"[build] Cython .pyd : {len(pyd_files)} pre-compiled modules")
    print(f"[build] LTO         : {'ON (--harden/--lto) — slow link at the end' if lto_on else 'off (faster)'}")
    print("-" * 70)
    print(f"[build] Compiling PyQt6 + Qt WebEngine — this takes about {est}.")
    print("[build] ****  DO NOT press Ctrl+C  ****  An interrupted build leaves")
    print("[build] an unusable dist. Let it run to the '[build] SUCCESS' line.")
    print("-" * 70)

    import time as _time
    _t0 = _time.time()
    try:
        result = subprocess.run(flags, cwd=package_root)
    finally:
        _mins = (_time.time() - _t0) / 60.0
        print(f"[build] Nuitka step ran for {_mins:.1f} min.")
        junction_cleanup()
        _cleanup_cython_artifacts(pyd_files, c_files)

    if result.returncode != 0:
        print("\n[build] FAILED. See Nuitka output above.")
        sys.exit(result.returncode)

    dist_dir = os.path.join(OUTPUT_DIR, "main.dist")
    exe_path = os.path.join(dist_dir, EXE_NAME)

    print("\n" + "=" * 70)
    print("[build] SUCCESS")
    print(f"[build] Dist folder  : {dist_dir}")
    print(f"[build] Executable   : {exe_path}")
    if use_cython and harden:
        print("[build] Protection   : Cython .pyd + Nuitka C++ + hardening (MAXIMUM)")
    elif use_cython:
        print("[build] Protection   : Cython .pyd + Nuitka C++")
    elif harden:
        print("[build] Protection   : Nuitka C++ + hardening")
    else:
        print("[build] Protection   : Nuitka C++ (standard)")
    print("=" * 70)
    print(
        "\nDISTRIBUTION NOTES:\n"
        "  * Ship the ENTIRE 'main.dist' folder, not just the .exe.\n"
        "  * python3*.dll and Qt/WebEngine files must stay next to the exe.\n"
        "  * Do NOT run from a Temp directory — the integrity check blocks that.\n"
        "  * Use Inno Setup with installer.iss to produce the student installer."
    )


if __name__ == "__main__":
    build()
