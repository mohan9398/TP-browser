# TP-Browser Build Guide

`build.py` produces a Windows standalone distribution with Nuitka and can
optionally precompile selected modules with Cython. The build is intentionally
**standalone**, not one-file: `main.py` rejects execution from a temporary
directory and requires the Python runtime DLLs beside the executable.

## Prerequisites

Install the checked-in dependency set:

```powershell
pip install -r requirements-build.txt
```

This installs Nuitka, Cython, PyQt6, PyQt6-WebEngine, psutil, pywifi,
cryptography, wheel, and setuptools. Nuitka also needs a supported C/C++
compiler. Its automatic MinGW download can be accepted when prompted, or a
compatible Visual Studio Build Tools installation can be used.

## Build commands

| Command | Current behavior |
|---|---|
| `python build.py` | Standard Nuitka standalone build |
| `python build.py --debug` | Keeps a console window for diagnostics |
| `python build.py --lto` | Enables Nuitka link-time optimization |
| `python build.py --harden` | Enables LTO, removes docstrings/asserts, disables `site`, uses static hashes, and enables anti-bloat |
| `python build.py --cython` | Precompiles the configured sensitive modules as `.pyd` files before Nuitka packaging |
| `python build.py --cython --harden` | Recommended production configuration in the current project |

Build time and output size depend on Python, the compiler, Qt version, cache
state, CPU, and selected flags; fixed time or size estimates are not guarantees.

## Cython stage

When `--cython` is present, `compile_cython_modules()` compiles these files in
place:

- `core/config.py`
- `core/secrets.py`
- `security/anti_debug.py`
- `security/process_monitor.py`
- `security/system_locker.py`
- `network/request_signer.py`
- `network/login_proxy.py`

Each module is converted to C and then to a Windows `.pyd` extension. Nuitka
packages those binary modules and compiles the remaining Python modules. The
temporary `.c`, `.pyd`, and compiler-output files created by the build are
removed in `finally` cleanup after Nuitka exits. If an individual Cython module
fails, the build continues and Nuitka compiles that module from Python source.

Edit `CYTHON_MODULES` in `build.py` to change this set. Cython and Nuitka make
casual source inspection harder, but they do not make client-side secrets or
logic impossible to recover.

## Package-name bridge

Source imports use `secure_browser.*`, while this checkout is normally named
`TP-browser`. `ensure_package_name()` handles that mismatch during a build:

1. It creates a temporary NTFS directory junction named `secure_browser` beside
   the checkout when necessary.
2. Nuitka runs from the parent directory against `secure_browser/main.py`.
3. The junction is removed after the build, including failed-build cleanup.

Do not distribute or manually retain this temporary junction.

## Nuitka output

Every mode creates:

```text
build/main.dist/
├── SecureBrowser.exe
├── python3*.dll
├── Qt/WebEngine libraries and resources
└── Python extension modules and other runtime dependencies
```

The build embeds the version read from `core/config.py`, applies `Browser.ico`
when present, disables the console except in `--debug` mode, and removes the
previous Nuitka output through `--remove-output`.

Keep the entire `build/main.dist/` directory together. Do not copy or distribute
only `SecureBrowser.exe`; the runtime integrity check and Qt WebEngine require
the supporting files.

## Installer packaging

The student-facing deliverable is built with `installer.iss` after Nuitka
succeeds:

1. Run the desired `build.py` command.
2. Open `installer.iss` in Inno Setup Compiler and build it.
3. The current script writes
   `installer/TPBrowser_Setup_1.0.0.exe`.

The installer:

- requires 64-bit-compatible Windows and administrator privileges;
- installs the complete `main.dist` tree under Program Files;
- keeps only the `en-US` Qt WebEngine locale;
- copies `core/labs.json` beside `SecureBrowser.exe`;
- creates Start Menu and common-desktop shortcuts; and
- uses a fixed `AppId` so later installers perform in-place upgrades.

Keep `AppVersion`, `VersionInfoVersion`, and `core/config.py:APP_VERSION` in sync
for every release. Never change the `AppId` after the first production release.

## Troubleshooting

### Cython is unavailable

```powershell
pip install -r requirements-build.txt
```

The standard Nuitka build does not require the optional `--cython` stage, but
the current dependency file installs Cython for both paths.

### Compiler not found

Allow Nuitka to download MinGW when prompted or install a supported Visual
Studio C/C++ toolchain. Installing a Python package named `mingw-w64` is not the
documented compiler setup for this project.

### Package import cannot be resolved

Check whether a conflicting `secure_browser` file or directory already exists
beside the repository. The build script reuses an existing path and cannot know
whether it points to this checkout.

### A Cython module fails

Read the per-module compiler output. Verify that its path remains in
`CYTHON_MODULES` and that the module is valid when compiled as a top-level
extension. The script falls back to Nuitka for failed modules.

### The built executable fails integrity checks

Run it from the complete `main.dist` directory or install it through Inno Setup.
Do not run a copied executable by itself or from `%TEMP%`.

## Release checklist

- Use `python build.py --cython --harden` for the current production profile.
- Test the application from the complete standalone directory.
- Build and test the Inno Setup installer, including upgrade and uninstall.
- Confirm `labs.json` contains production portal URLs.
- Confirm build and installer versions match.
- Code-sign the executable and installer for production distribution.
- Follow `PRODUCTION_DEPLOYMENT.md` before release.
