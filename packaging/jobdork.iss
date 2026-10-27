; Inno Setup script for the Windows installer. packaging/build.py runs it
; with /DVersion, /DSource (PyInstaller's dist\jobdork), /DIcon and /DOutput.
;
; Installs for the current user only, so no administrator prompt. Settings,
; job posts and the resume live in %LOCALAPPDATA%\jobdork, not here. An
; uninstall always removes the scheduled scan (a Task Scheduler task that
; would otherwise go on starting a program that is gone) and the window's
; storage, and asks, item by item, what of the person's to delete as well:
; nothing is ticked, so a reinstall finds whatever they kept. The removing is
; jobdork's own (jobdork.exe --uninstall, core/uninstall.py), the same as on
; the Settings page and `jobdork uninstall`.
;
; privacy.txt is shown before installing ("Information" page): what jobdork
; keeps, what it sends where, and how to turn off the one thing it does by
; itself (the daily version check): software that goes on the network
; unasked should say so before it is installed. Keep it in step with
; PRIVACY.md.

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
; Relative to this script's folder.
InfoBeforeFile=privacy.txt
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID ties Windows notifications (toasts) to jobdork's name and
; icon; it must match notify.APP_ID in jobdork/core/notify.py.
Name: "{group}\jobdork"; Filename: "{app}\jobdork.exe"; AppUserModelID: "io.github.jessn-dev.jobdork"
Name: "{autodesktop}\jobdork"; Filename: "{app}\jobdork.exe"; Tasks: desktopicon; AppUserModelID: "io.github.jessn-dev.jobdork"

[Run]
Filename: "{app}\jobdork.exe"; Description: "{cm:LaunchProgram,jobdork}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Before the program's files go, while jobdork.exe is still there to run.
Filename: "{app}\jobdork.exe"; Parameters: "--uninstall {code:RemoveChoices}"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveTraces"

[Code]
var
  Choices: String;

{ What the person ticked, comma separated, for jobdork.exe --uninstall. }
function RemoveChoices(Param: String): String;
begin
  Result := Choices;
end;

{ Asks, item by item, what of theirs to delete. Nothing is ticked: what is
  not ticked is kept. Cancel stops the uninstall. A silent uninstall asks
  nothing and keeps everything. The keys match core/uninstall.py ITEMS. }
function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  Intro: TNewStaticText;
  Boxes: array[0..6] of TNewCheckBox;
  Keys: array[0..6] of String;
  Labels: array[0..6] of String;
  OkButton, CancelButton: TNewButton;
  I, Top: Integer;
begin
  Result := True;
  Choices := '';
  if UninstallSilent() then
    Exit;
  Keys[0] := 'settings';  Labels[0] := 'Settings: what you search for, where, pay, the AI page';
  Keys[1] := 'jobs';      Labels[1] := 'Job posts, with your statuses, notes, AI verdicts and backups';
  Keys[2] := 'resume';    Labels[2] := 'Your resume';
  Keys[3] := 'documents'; Labels[3] := 'Letters and tailored resumes jobdork wrote';
  Keys[4] := 'keys';      Labels[4] := 'Saved job-source keys (Adzuna, USAJOBS)';
  Keys[5] := 'logs';      Labels[5] := 'Logs';
  Keys[6] := 'downloads'; Labels[6] := 'Installers the Update button left in Downloads';
  Form := CreateCustomForm();
  try
    Form.Caption := 'Uninstall jobdork';
    Form.ClientWidth := ScaleX(480);
    Form.ClientHeight := ScaleY(340);
    Intro := TNewStaticText.Create(Form);
    Intro.Parent := Form;
    Intro.Left := ScaleX(16);
    Intro.Top := ScaleY(14);
    Intro.Width := Form.ClientWidth - ScaleX(32);
    Intro.AutoSize := False;
    Intro.Height := ScaleY(48);
    Intro.WordWrap := True;
    Intro.Caption := 'jobdork and its scheduled scan will be removed. Tick what of yours to ' +
      'delete as well. Anything not ticked is kept, so a reinstall finds it.';
    Top := ScaleY(70);
    for I := 0 to 6 do
    begin
      Boxes[I] := TNewCheckBox.Create(Form);
      Boxes[I].Parent := Form;
      Boxes[I].Left := ScaleX(16);
      Boxes[I].Top := Top;
      Boxes[I].Width := Form.ClientWidth - ScaleX(32);
      Boxes[I].Caption := Labels[I];
      Boxes[I].Checked := False;
      Top := Top + ScaleY(28);
    end;
    OkButton := TNewButton.Create(Form);
    OkButton.Parent := Form;
    OkButton.Caption := 'Uninstall';
    OkButton.Width := ScaleX(90);
    OkButton.Left := Form.ClientWidth - ScaleX(200);
    OkButton.Top := Form.ClientHeight - ScaleY(44);
    OkButton.ModalResult := mrOk;
    OkButton.Default := True;
    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := 'Cancel';
    CancelButton.Width := ScaleX(90);
    CancelButton.Left := Form.ClientWidth - ScaleX(104);
    CancelButton.Top := OkButton.Top;
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;
    if Form.ShowModal() = mrOk then
    begin
      for I := 0 to 6 do
        if Boxes[I].Checked then
        begin
          if Choices <> '' then
            Choices := Choices + ',';
          Choices := Choices + Keys[I];
        end;
    end
    else
      Result := False;
  finally
    Form.Free();
  end;
end;
