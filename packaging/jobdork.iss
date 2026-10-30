; Inno Setup script for the Windows installer. packaging/build.py runs it
; with /DVersion, /DSource (PyInstaller's dist\jobdork), /DIcon and /DOutput.
;
; Installs for the current user only, so no administrator prompt. Settings,
; job posts and the resume live in %LOCALAPPDATA%\jobdork, not here. An
; uninstall always removes the scheduled scan (a Task Scheduler task that
; would otherwise go on starting a program that is gone), the window's
; storage and any keys kept in Credential Manager, and asks, item by item,
; what of the person's to delete as well:
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
; The name under Installed apps. Without it Windows shows "jobdork version
; 0.15.2", and WinGet matches a package by this name (scripts/winget_manifest.py).
UninstallDisplayName=jobdork
OutputDir={#Output}
OutputBaseFilename=jobdork-{#Version}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
; Inno draws the controls itself in the windows11 style: Windows' own tick
; boxes came out cut off on a screen at high scaling (0.15.2).
WizardStyle=modern windows11
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
; The app's own Update runs this installer silently with /restart=yes: then
; it opens the new version. A silent install without it (WinGet) opens nothing.
Filename: "{app}\jobdork.exe"; Flags: nowait; Check: RestartAfter

[UninstallRun]
; Before the program's files go, while jobdork.exe is still there to run.
Filename: "{app}\jobdork.exe"; Parameters: "--uninstall {code:RemoveChoices}"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveTraces"

[Code]
var
  Choices: String;

{ /restart=yes, from the app's Update: open jobdork once it is installed. }
function RestartAfter: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:restart|no}') = 'yes');
end;

{ What the person ticked, comma separated, for jobdork.exe --uninstall. }
function RemoveChoices(Param: String): String;
begin
  Result := Choices;
end;

{ Asks, item by item, what of theirs to delete. Nothing is ticked: what is
  not ticked is kept. Cancel stops the uninstall. A silent uninstall asks
  nothing and keeps everything. The keys match core/uninstall.py ITEMS.

  Laid out as the installer's pages are: a white band with a bold title and
  a line under it, the choices, a line, then the buttons at the installer's
  size. Every size goes through ScaleX/ScaleY once, and the form is told to
  keep it (KeepSizeX/KeepSizeY True): left to Inno, a screen at 150-200%
  scaled it a second time, filling the screen with clipped text (0.15.2). }
function InitializeUninstall(): Boolean;
var
  Form: TSetupForm;
  Band: TPanel;
  Title, Subtitle, Intro: TNewStaticText;
  TopLine, BottomLine: TBevel;
  Boxes: array[0..5] of TNewCheckBox;
  Keys: array[0..5] of String;
  Labels: array[0..5] of String;
  OkButton, CancelButton: TNewButton;
  I, Top, Inset: Integer;
begin
  Result := True;
  Choices := '';
  if UninstallSilent() then
    Exit;
  Keys[0] := 'settings';  Labels[0] := 'Settings: what you search for, where, pay, the AI page';
  Keys[1] := 'jobs';      Labels[1] := 'Job posts, with your statuses, notes, AI verdicts and backups';
  Keys[2] := 'resume';    Labels[2] := 'Your resume';
  Keys[3] := 'documents'; Labels[3] := 'Letters and tailored resumes jobdork wrote';
  Keys[4] := 'logs';      Labels[4] := 'Logs';
  Keys[5] := 'downloads'; Labels[5] := 'Installers the Update button left in Downloads';
  { ClientWidth, ClientHeight, KeepSizeX, KeepSizeY. }
  Form := CreateCustomForm(ScaleX(500), ScaleY(380), True, True);
  try
    Form.Caption := 'Uninstall jobdork';
    Form.Position := poScreenCenter;
    Inset := ScaleX(40);

    Band := TPanel.Create(Form);
    Band.Parent := Form;
    Band.Left := 0;
    Band.Top := 0;
    Band.Width := Form.ClientWidth;
    Band.Height := ScaleY(58);
    Band.BevelOuter := bvNone;
    Band.Color := clWindow;

    Title := TNewStaticText.Create(Form);
    Title.Parent := Band;
    Title.Left := ScaleX(24);
    Title.Top := ScaleY(12);
    Title.Font.Style := [fsBold];
    Title.Caption := 'Remove jobdork';

    Subtitle := TNewStaticText.Create(Form);
    Subtitle.Parent := Band;
    Subtitle.Left := Inset;
    Subtitle.Top := ScaleY(32);
    Subtitle.Caption := 'Choose what of yours to delete as well.';

    TopLine := TBevel.Create(Form);
    TopLine.Parent := Form;
    TopLine.Shape := bsTopLine;
    TopLine.Left := 0;
    TopLine.Top := Band.Height;
    TopLine.Width := Form.ClientWidth;
    TopLine.Height := ScaleY(2);

    Intro := TNewStaticText.Create(Form);
    Intro.Parent := Form;
    Intro.AutoSize := False;
    Intro.WordWrap := True;
    Intro.Left := Inset;
    Intro.Top := Band.Height + ScaleY(14);
    Intro.Width := Form.ClientWidth - 2 * Inset;
    Intro.Height := ScaleY(56);
    Intro.Caption := 'jobdork, its scheduled scan and any keys it kept in Credential Manager ' +
      'will be removed. Tick what of yours to delete as well. Anything not ticked is kept, ' +
      'so a reinstall finds it.';

    Top := Intro.Top + Intro.Height + ScaleY(6);
    for I := 0 to 5 do
    begin
      Boxes[I] := TNewCheckBox.Create(Form);
      Boxes[I].Parent := Form;
      Boxes[I].Left := Inset;
      Boxes[I].Top := Top;
      Boxes[I].Width := Form.ClientWidth - 2 * Inset;
      Boxes[I].Height := ScaleY(21);
      Boxes[I].Caption := Labels[I];
      Boxes[I].Checked := False;
      Top := Top + ScaleY(26);
    end;

    BottomLine := TBevel.Create(Form);
    BottomLine.Parent := Form;
    BottomLine.Shape := bsTopLine;
    BottomLine.Left := 0;
    BottomLine.Top := Form.ClientHeight - ScaleY(48);
    BottomLine.Width := Form.ClientWidth;
    BottomLine.Height := ScaleY(2);

    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Caption := 'Cancel';
    CancelButton.Width := ScaleX(75);
    CancelButton.Height := ScaleY(23);
    CancelButton.Left := Form.ClientWidth - ScaleX(10) - CancelButton.Width;
    CancelButton.Top := Form.ClientHeight - ScaleY(36);
    CancelButton.ModalResult := mrCancel;
    CancelButton.Cancel := True;

    OkButton := TNewButton.Create(Form);
    OkButton.Parent := Form;
    OkButton.Caption := 'Uninstall';
    OkButton.Width := ScaleX(75);
    OkButton.Height := ScaleY(23);
    OkButton.Left := CancelButton.Left - ScaleX(10) - OkButton.Width;
    OkButton.Top := CancelButton.Top;
    OkButton.ModalResult := mrOk;
    OkButton.Default := True;

    if Form.ShowModal() = mrOk then
    begin
      for I := 0 to 5 do
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
