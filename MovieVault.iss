#define MyAppName "MovieVault v2"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "MovieVault Personal Library"
#define MyAppExeName "MovieVault.exe"
[Setup]
AppId={{C3898D66-FB46-4DD3-9768-8C7A47043F4A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName=MovieVault 2.0 Release Candidate
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MovieVaultV2
DefaultGroupName=MovieVault v2
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=release
OutputBaseFilename=MovieVault_Setup_v2.0.0_RC1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
DirExistsWarning=no
VersionInfoVersion=2.0.0.1
SetupIconFile=assets\movievault.ico
LicenseFile=docs\LICENSE.txt
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
[Files]
Source: "dist\MovieVault\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\MovieVault v2"; Filename: "{app}\MovieVault.exe"
Name: "{autodesktop}\MovieVault v2"; Filename: "{app}\MovieVault.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\MovieVault.exe"; Description: "Launch MovieVault"; Flags: nowait postinstall skipifsilent
[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  PreviousExe: string;
  ExitCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    PreviousExe := ExpandConstant('{app}\MovieVault.exe');
    if FileExists(PreviousExe) then
    begin
      if not Exec(PreviousExe, '--backup-only', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      begin
        MsgBox('Could not start the safety backup of your existing MovieVault library. Installation has been stopped.', mbError, MB_OK);
        Abort;
      end;
      if ExitCode <> 0 then
      begin
        MsgBox('The old library could not be backed up. Installation has been stopped to protect your data.', mbError, MB_OK);
        Abort;
      end;
    end;
  end;
end;
