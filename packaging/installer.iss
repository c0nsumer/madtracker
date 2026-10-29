; Inno Setup script. build_windows.ps1 passes the version:
;   ISCC.exe /DAppVersion=0.0.1 packaging\installer.iss
; The output lands in dist\ next to the PyInstaller folder.
#ifndef AppVersion
  #error Pass the version with /DAppVersion=x.y.z
#endif

#define AppName "MadTracker"
#define AppExe "MadTracker.exe"

[Setup]
; Never change AppId. Inno Setup uses it to find and upgrade an existing
; install, and the [Code] below uses it to find that install's uninstaller.
AppId={{6B0F7C2E-3D41-4C8A-9E55-7A1D2B94F0C3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Steve Vigneau (nuxx.net)
; Per-user install: no admin prompt on a venue laptop.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\MadTracker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Windows 10 is the minimum.
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=MadTracker-{#AppVersion}-setup
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
#ifexist "madtracker.ico"
SetupIconFile=madtracker.ico
#endif
; The wizard's pictures: build_windows.ps1 draws them with
; tools/make_installer_images.py (they are not committed), one file per
; display scale so Inno Setup can pick the closest instead of stretching.
#ifexist "wizard\welcome-202x386.bmp"
WizardImageFile=wizard\welcome-202x386.bmp,wizard\welcome-269x515.bmp,wizard\welcome-336x643.bmp,wizard\welcome-403x772.bmp,wizard\welcome-430x824.bmp,wizard\welcome-498x953.bmp,wizard\welcome-534x1022.bmp
#endif
#ifexist "wizard\header-58x58.bmp"
WizardSmallImageFile=wizard\header-58x58.bmp,wizard\header-77x77.bmp,wizard\header-97x97.bmp,wizard\header-116x116.bmp,wizard\header-124x124.bmp,wizard\header-143x143.bmp,wizard\header-159x159.bmp
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MadTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; There is no [UninstallDelete] section on purpose. The data folder,
; {localappdata}\MadTracker, holds race results and backups, and goes
; only when the person uninstalling says so (CurUninstallStepChanged).

[Code]
// Installing over an older version replaces its files but, on its own,
// leaves behind any file the new version no longer ships (a library
// PyInstaller stopped bundling, say). Running the old version's own
// uninstaller first keeps the program folder exact. It runs at the
// install step, after the wizard has read the previous choices (the
// desktop icon task) from the registry entry the uninstall removes, and
// silently, so the user sees one installer and not two. The uninstaller
// removes only what its installer put under {app}; the data folder is
// never its business.
function PreviousUninstaller(): String;
var
  Key: String;
begin
  Result := '';
  Key := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1');
  // HKA is the current user's hive for this per-user install, and the
  // machine's for an install that was run elevated.
  if not RegQueryStringValue(HKA, Key, 'UninstallString', Result) then
    Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Uninstaller: String;
  ResultCode: Integer;
begin
  if CurStep <> ssInstall then
    exit;
  Uninstaller := PreviousUninstaller();
  if Uninstaller = '' then
    exit;
  Exec(RemoveQuotes(Uninstaller), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// The data folder is a venue's whole history, so the uninstaller asks
// before it goes, No by default. Never when silent:
// an upgrade runs the old uninstaller silently, and must keep the data.
// Only the default folder and the app's remembered settings go; a data
// file kept elsewhere, and a backup folder chosen in Settings, are the
// venue's own and stay.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep <> usPostUninstall) or UninstallSilent() then
    exit;
  DataDir := ExpandConstant('{localappdata}\MadTracker');
  if not DirExists(DataDir) then
    exit;
  if MsgBox('Also delete MadTracker''s data: riders, events, results, and backups?' + #13#10#13#10 +
      'This deletes this folder and cannot be undone:' + #13#10 + DataDir + #13#10#13#10 +
      'Data files saved elsewhere, and a backup folder chosen in Settings, are not deleted.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> IDYES then
    exit;
  if not DelTree(DataDir, True, True, True) then
    MsgBox('Some files could not be deleted. If MadTracker is still open, close it and delete this folder by hand:' + #13#10 + DataDir,
      mbError, MB_OK);
  // Qt's remembered settings (the last data file, the scoreboard display).
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\madtracker');
end;
