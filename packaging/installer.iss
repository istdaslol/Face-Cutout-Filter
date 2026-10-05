; =============================================================================
; Gesichtsfilter - Inno Setup 6 (https://jrsoftware.org/isinfo.php)
;
; Bauen (nach "python packaging/build.py", siehe packaging/make_installer.py):
;   iscc /DMyAppVersion=0.3.0 packaging\installer.iss
; Ergebnis: installer_out\Gesichtsfilter-Setup-<Version>.exe
;
; Optionale Komponente "Unity Capture" (virtuelle Kamera mit eigenem Namen):
;   - DLLs kommen aus packaging\unitycapture\ (packaging\fetch_unitycapture.py, gepinnt + SHA256)
;   - Der Name wird auf einer eigenen Seite abgefragt, per Kommandozeile mit /CAMNAME="Name"
;   - Das Programm liest den Namen aus {app}\unitycapture_name.txt (siehe io\vcam.py)
; Installation braucht Administratorrechte (Registrierung des DirectShow-Filters).
; =============================================================================

; ---- Konstanten (hier anpassen) --------------------------------------------
#define MyAppName      "Gesichtsfilter"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppExe       "Gesichtsfilter.exe"
#define MyAppPublisher "Gesichtsfilter"
; Standardname der Unity-Capture-Kamera:
#define DefaultCamName "Gesichtsfilter"
#define NameFile       "unitycapture_name.txt"
#define DistDir        "..\dist\Gesichtsfilter"
#define UcDir          "unitycapture"

[Setup]
; Feste ID: erlaubt Updates ueber eine vorhandene Installation. NICHT aendern.
AppId={{C35D1EDD-809D-4AC0-BEE3-93A177C1DF6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExe}
SetupIconFile=..\assets\app.ico
OutputDir=..\installer_out
OutputBaseFilename=Gesichtsfilter-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Das Programm laeuft sonst nach "Fertigstellen" nicht mit erhoehten Rechten weiter
; (siehe [Run]: runasoriginaluser)

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Types]
Name: "standard"; Description: "Standardinstallation"
Name: "custom"; Description: "Benutzerdefiniert"; Flags: iscustom

[Components]
Name: "main"; Description: "Gesichtsfilter"; Types: standard custom; Flags: fixed
Name: "unity"; Description: "Unity Capture (virtuelle Kamera mit eigenem Namen)"; Types: custom; ExtraDiskSpaceRequired: 400000

[Tasks]
Name: "desktopicon"; Description: "Symbol auf dem Desktop erstellen"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
Source: "{#UcDir}\UnityCaptureFilter32.dll"; DestDir: "{app}\unitycapture"; Flags: ignoreversion restartreplace uninsrestartdelete; Components: unity
Source: "{#UcDir}\UnityCaptureFilter64.dll"; DestDir: "{app}\unitycapture"; Flags: ignoreversion restartreplace uninsrestartdelete; Components: unity
Source: "UnityCapture-LICENSE.txt"; DestDir: "{app}\unitycapture"; Flags: ignoreversion; Components: unity

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{#MyAppName} starten"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
Type: files; Name: "{app}\{#NameFile}"

[Code]
var
  NamePage: TInputQueryWizardPage;

function CamName(Param: String): String;
begin
  // Gewaehlter Kameraname (nach der Namensseite validiert)
  Result := Trim(NamePage.Values[0]);
  if Result = '' then Result := '{#DefaultCamName}';
end;

procedure InitializeWizard;
begin
  NamePage := CreateInputQueryPage(wpSelectComponents,
    'Name der virtuellen Kamera',
    'Unter welchem Namen soll Unity Capture erscheinen?',
    'Dieser Name steht danach in Zoom, Discord, OBS usw. in der Kameraliste. ' +
    'Er kann nicht ' + #34 + ' oder % enthalten (maximal 60 Zeichen). ' +
    'Hinweis: Ist Unity Capture schon von anderer Stelle installiert, wird es durch diese Version ersetzt.');
  NamePage.Add('Kameraname:', False);
  // Stille Installation: Setup.exe /VERYSILENT /COMPONENTS="main,unity" /CAMNAME="Mein Name"
  NamePage.Values[0] := ExpandConstant('{param:CAMNAME|{#DefaultCamName}}');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = NamePage.ID) and (not WizardIsComponentSelected('unity'));
end;

function NameIsValid(const N: String): Boolean;
begin
  Result := (Length(N) <= 60) and (Pos(#34, N) = 0) and (Pos('%', N) = 0);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  N: String;
begin
  Result := True;
  if CurPageID = NamePage.ID then
  begin
    N := Trim(NamePage.Values[0]);
    if N = '' then N := '{#DefaultCamName}';
    if not NameIsValid(N) then
    begin
      MsgBox('Der Name darf h' + #246 + 'chstens 60 Zeichen lang sein und weder ' + #34 + ' noch % enthalten.', mbError, MB_OK);
      Result := False;
    end
    else
      NamePage.Values[0] := N;
  end;
end;

// Fuehrt regsvr32 aus. Parameter 32-Bit-DLL: ueber {syswow64}, 64-Bit-DLL: ueber {sys} (nativ).
function RegSvr(const Dll32Bit: Boolean; const Params: String): Boolean;
var
  Exe: String;
  Code: Integer;
begin
  if Dll32Bit then Exe := ExpandConstant('{syswow64}\regsvr32.exe')
  else Exe := ExpandConstant('{sys}\regsvr32.exe');
  Result := Exec(Exe, Params, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

function DllPath(const Name: String): String;
begin
  Result := ExpandConstant('{app}\unitycapture\') + Name;
end;

procedure UnregisterUnity;
begin
  // Fehler hier sind unkritisch (z.B. nie registriert): nur versuchen
  if FileExists(DllPath('UnityCaptureFilter64.dll')) then RegSvr(False, '/s /u "' + DllPath('UnityCaptureFilter64.dll') + '"');
  if FileExists(DllPath('UnityCaptureFilter32.dll')) then RegSvr(True, '/s /u "' + DllPath('UnityCaptureFilter32.dll') + '"');
end;

procedure SaveCamName(const N: String);
var
  Lines: TArrayOfString;
begin
  SetArrayLength(Lines, 1);
  Lines[0] := N;
  SaveStringsToUTF8File(ExpandConstant('{app}\{#NameFile}'), Lines, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  N, Failed: String;
begin
  if CurStep = ssInstall then
  begin
    // Update/Neuinstallation: alte Registrierung (evtl. anderer Name) vorher entfernen
    UnregisterUnity;
  end
  else if CurStep = ssPostInstall then
  begin
    if WizardIsComponentSelected('unity') then
    begin
      N := CamName('');
      Failed := '';
      // Syntax wie in Install\InstallCustomName.bat des Projekts
      if not RegSvr(False, '/s "' + DllPath('UnityCaptureFilter64.dll') + '" "/i:UnityCaptureName=' + N + '"') then
        Failed := Failed + ' 64-Bit';
      if not RegSvr(True, '/s "' + DllPath('UnityCaptureFilter32.dll') + '" "/i:UnityCaptureName=' + N + '"') then
        Failed := Failed + ' 32-Bit';
      if Failed = '' then
        SaveCamName(N)
      else
      begin
        DeleteFile(ExpandConstant('{app}\{#NameFile}'));
        SuppressibleMsgBox('Unity Capture konnte nicht registriert werden (' + Trim(Failed) + ').' + #13#10 +
          'Gesichtsfilter ist trotzdem installiert; die Vorschau und OBS Virtual Camera funktionieren.',
          mbError, MB_OK, IDOK);
      end;
    end
    else
      DeleteFile(ExpandConstant('{app}\{#NameFile}')); // Rest einer fruehren Installation
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then UnregisterUnity; // vor dem Loeschen der DLLs
end;
