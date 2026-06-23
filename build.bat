@echo off
REM ============================================================================
REM  Secure Exam Browser - Nuitka production build (Windows)
REM  Produces the SAME standalone .exe output as build.py, just without the
REM  Python wrapper. Double-click this file or run it from a terminal.
REM
REM  REQUIREMENTS:
REM    pip install nuitka PyQt6 PyQt6-WebEngine psutil pywifi
REM    (Nuitka will offer to auto-download a C compiler on first run.)
REM ============================================================================

setlocal enabledelayedexpansion

REM --- Resolve folders --------------------------------------------------------
REM  PROJECT_DIR = folder this .bat lives in (the TP-browser folder)
set "PROJECT_DIR=%~dp0"
REM  strip trailing backslash
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
for %%I in ("%PROJECT_DIR%") do set "PARENT_DIR=%%~dpI"
if "%PARENT_DIR:~-1%"=="\" set "PARENT_DIR=%PARENT_DIR:~0,-1%"

set "PKG_NAME=secure_browser"
set "LINK_PATH=%PARENT_DIR%\%PKG_NAME%"
set "CREATED_LINK=0"

REM --- Bridge the package name (folder is TP-browser, imports use secure_browser)
for %%I in ("%PROJECT_DIR%") do set "FOLDER_NAME=%%~nxI"
if /I "%FOLDER_NAME%"=="%PKG_NAME%" (
    set "RUN_DIR=%PARENT_DIR%"
) else (
    set "RUN_DIR=%PARENT_DIR%"
    if not exist "%LINK_PATH%" (
        echo [build] Creating temporary junction: %LINK_PATH% -^> %PROJECT_DIR%
        mklink /J "%LINK_PATH%" "%PROJECT_DIR%" >nul
        if errorlevel 1 (
            echo [build] ERROR: could not create junction. Run from the parent folder
            echo         or rename this folder to "secure_browser".
            exit /b 1
        )
        set "CREATED_LINK=1"
    )
)

REM --- Build ------------------------------------------------------------------
echo [build] Running Nuitka...
pushd "%RUN_DIR%"

python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --enable-plugin=pyqt6 ^
    --include-package=secure_browser ^
    --include-package=psutil ^
    --include-package=pywifi ^
    --output-dir="%PROJECT_DIR%\build" ^
    --output-filename=SecureBrowser.exe ^
    --remove-output ^
    --windows-console-mode=disable ^
    --company-name=TeleUniv ^
    --product-name="Secure Exam Browser" ^
    --file-description="Secure Exam Browser" ^
    --file-version=1.0.0.0 ^
    --product-version=1.0.0 ^
    secure_browser\main.py

set "BUILD_RC=%errorlevel%"
popd

REM --- Cleanup the temporary junction ----------------------------------------
if "%CREATED_LINK%"=="1" (
    echo [build] Removing temporary junction: %LINK_PATH%
    rmdir "%LINK_PATH%"
)

REM --- Result -----------------------------------------------------------------
if not "%BUILD_RC%"=="0" (
    echo.
    echo [build] FAILED. See Nuitka output above.
    exit /b %BUILD_RC%
)

echo.
echo ============================================================
echo [build] SUCCESS
echo [build] Folder : %PROJECT_DIR%\build\main.dist
echo [build] Exe    : %PROJECT_DIR%\build\main.dist\SecureBrowser.exe
echo ============================================================
echo.
echo Ship the ENTIRE main.dist folder, not just the .exe.
echo Do NOT run it from a Temp directory (integrity check blocks that).
echo.

endlocal
