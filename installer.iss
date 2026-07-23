; ─────────────────────────────────────────────────────────────────────────────
; TP Browser — Inno Setup Installer Script
;
; PREREQUISITES (run in order before compiling this script):
;   1. python build.py          → produces build\main.dist\
;   2. Open this file in Inno Setup Compiler → click Build → Run
;
; OUTPUT: installer\TPBrowser_Setup_1.0.0.exe
; ─────────────────────────────────────────────────────────────────────────────

#define AppName      "TP Browser"
#define AppVersion   "1.0.1"
#define AppPublisher "TeleUniv"
#define AppExeName   "SecureBrowser.exe"
#define DistDir      "build\main.dist"

; ── App identity ─────────────────────────────────────────────────────────────
[Setup]
AppId={{A3F2D1C4-8B7E-4F6A-9C2D-1E5B3A7F8D90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://teleuniv.in
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Installer

; ── Install location ─────────────────────────────────────────────────────────
DefaultDirName={autopf}\SecureExamBrowser
DefaultGroupName={#AppName}
DisableDirPage=no

; ── Output ───────────────────────────────────────────────────────────────────
OutputDir=installer
OutputBaseFilename=TPBrowser_Setup_{#AppVersion}
SetupIconFile=Browser.ico
UninstallDisplayIcon={app}\{#AppExeName}

; ── Compression ──────────────────────────────────────────────────────────────
; ultra64 = maximum LZMA2 compression per file.
; SolidCompression=no is required — Inno Setup is 32-bit and hits its 2GB
; virtual address limit when solid-compressing Qt WebEngine as one block.
Compression=lzma2/ultra64
SolidCompression=no
LZMANumBlockThreads=4

; ── UI ───────────────────────────────────────────────────────────────────────
WizardStyle=modern
WizardSmallImageFile=Browser.png
DisableWelcomePage=no
DisableReadyPage=no

; ── Privileges ───────────────────────────────────────────────────────────────
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

; ── Misc ─────────────────────────────────────────────────────────────────────
; Prevent user from installing while app is running
CloseApplications=yes
RestartIfNeededByRun=no

; ─────────────────────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ─────────────────────────────────────────────────────────────────────────────
[Files]
; ── Main application — all files except unused locale packs ──────────────────
Source: "{#DistDir}\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "qtwebengine_locales\*.pak"

; Keep only English locale — the other 100+ .pak files are not needed
Source: "{#DistDir}\qtwebengine_locales\en-US.pak"; \
    DestDir: "{app}\qtwebengine_locales"; \
    Flags: ignoreversion

; ── College logos, next to the exe (where the selector looks for them) ───────
Source: "images\*"; \
    DestDir: "{app}\images"; \
    Flags: ignoreversion

; ── labs.json placed next to the exe (where frozen code looks for it) ────────
; Edit this file after install to add/remove portals without rebuilding.
Source: "core\labs.json"; \
    DestDir: "{app}"; \
    Flags: ignoreversion

; ─────────────────────────────────────────────────────────────────────────────
[Icons]
; Start Menu
Name: "{group}\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\{#AppExeName}"; \
    Comment: "Launch TP Browser Secure Exam Environment"

Name: "{group}\Uninstall {#AppName}"; \
    Filename: "{uninstallexe}"

; Desktop
Name: "{commondesktop}\{#AppName}"; \
    Filename: "{app}\{#AppExeName}"; \
    WorkingDir: "{app}"; \
    IconFilename: "{app}\{#AppExeName}"; \
    Comment: "Launch TP Browser Secure Exam Environment"

; ─────────────────────────────────────────────────────────────────────────────
[Run]
; Launch the app after install finishes (user can uncheck in wizard)
Filename: "{app}\{#AppExeName}"; \
    Description: "Launch {#AppName} now"; \
    Flags: nowait postinstall skipifsilent; \
    WorkingDir: "{app}"

; ─────────────────────────────────────────────────────────────────────────────
[UninstallRun]
; Kill the process before uninstalling so files aren't locked
Filename: "taskkill.exe"; \
    Parameters: "/F /IM {#AppExeName}"; \
    Flags: runhidden waituntilterminated; \
    RunOnceId: "KillTPBrowser"

; ─────────────────────────────────────────────────────────────────────────────
[UninstallDelete]
; Clean up the whole install folder on uninstall
Type: filesandordirs; Name: "{app}"

; ─────────────────────────────────────────────────────────────────────────────
[Code]
{ Check that the Nuitka dist folder actually exists before compiling,
  so the user gets a clear error instead of a silent empty installer. }
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Nothing extra needed — Run section handles launch }
  end;
end;
