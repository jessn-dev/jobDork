; Inno Setup script for the Windows installer. packaging/build.py runs it
; with /DVersion, /DSource (PyInstaller's dist\jobdork), /DIcon and /DOutput.
;
; Installs for the current user only, so no administrator prompt. Settings,
; job posts and the resume live in %LOCALAPPDATA%\jobdork, not here, and an
; uninstall leaves them: they are the user's, and a reinstall should find them.

[Setup]
; Never change AppId: it is how Windows knows a new version replaces this one.
AppId={{89BA0AFD-43DD-4F5C-ADC2-221D5F8E1EA6}
AppName=jobdork
AppVersion={#Version}
AppPublisher=jessn-dev
AppPublisherURL=https://github.com/jessn-dev/jobDork
DefaultDirName={autopf}\jobdork
DefaultGroupName=jobdork
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\jobdork.exe
OutputDir={#Output}
OutputBaseFilename=jobdork-{#Version}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\jobdork"; Filename: "{app}\jobdork.exe"
Name: "{autodesktop}\jobdork"; Filename: "{app}\jobdork.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\jobdork.exe"; Description: "{cm:LaunchProgram,jobdork}"; Flags: nowait postinstall skipifsilent
