; ─── Knack Installer Script ────────────────────────────────────
; Inno Setup 6.x

#define MyAppName "Knack"
; Версию НЕ дублируем: берём из собранного exe, а туда она попадает из
; knack/core/constants.py (см. Knack.spec). Поднять версию = поправить одну
; строку в constants.py и пересобрать.
#define MyAppExe "dist\Knack.exe"
#if !FileExists(AddBackslash(SourcePath) + MyAppExe)
  #error Сначала соберите exe: pyinstaller --clean --noconfirm Knack.spec
#endif
#define MyAppVersion GetStringFileInfo(AddBackslash(SourcePath) + MyAppExe, PRODUCT_VERSION)
#if MyAppVersion == ""
  #error В exe нет ресурса версии. Пересоберите его текущей Knack.spec.
#endif
#define MyAppExeName "Knack.exe"
#define MyAppPublisher "SmeshidoJoe"
#define MyAppUrl "https://github.com/SmeshidoJoe/Knack"

[Setup]
AppId={{359AA92A-4D8D-42B0-B83C-6D4F020B1795}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}
AppUpdatesURL={#MyAppUrl}/releases

; Ставим в папку программ текущего пользователя: при PrivilegesRequired=lowest
; это %LOCALAPPDATA%\Programs, куда можно писать без прав администратора. Это
; понадобится обновлению, которое подменяет exe на месте — в Program Files
; подмена молча не пройдёт.
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest

OutputDir=installer_output
OutputBaseFilename=Knack-Setup-{#MyAppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Knack держит один экземпляр на именованном мьютексе и сидит в трее. Если его
; не закрыть, установщик не сможет заменить exe.
CloseApplications=yes
RestartApplications=no
AppMutex=Knack-Single-Instance-Mutex

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.DirNotWritable=This folder cannot be written to without administrator rights.%n%nKnack updates itself and needs write access to its own folder, so please pick another location — for example the default one.
russian.DirNotWritable=В эту папку нельзя записывать без прав администратора.%n%nKnack обновляет себя сам и должен иметь доступ на запись в свою папку, поэтому выберите другое место — например, предложенное по умолчанию.
english.KeepData=Keep settings, shelf and notes
russian.KeepData=Оставить настройки, полку и заметки

[Code]
// Проверяем, что в выбранную папку можно писать БЕЗ прав администратора.
// Иначе пользователь выберет Program Files, установка пройдёт, а обновление
// потом будет молча отказывать.
function NextButtonClick(CurPageID: Integer): Boolean;
var
  Probe: string;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    Exit;
  ForceDirectories(WizardDirValue);
  Probe := AddBackslash(WizardDirValue) + 'knack_write_test.tmp';
  if SaveStringToFile(Probe, 'x', False) then
    DeleteFile(Probe)
  else begin
    Result := False;
    MsgBox(ExpandConstant('{cm:DirNotWritable}'), mbError, MB_OK);
  end;
end;

// При удалении спрашиваем, оставлять ли данные пользователя. Молча стирать
// полку с заметками нельзя, молча оставлять мусор — тоже некрасиво.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant('{userappdata}\{#MyAppName}');
  if not DirExists(DataDir) then
    Exit;
  if MsgBox(ExpandConstant('{cm:KeepData}') + '?', mbConfirmation, MB_YESNO) = IDNO then
    DelTree(DataDir, True, True, True);
end;

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startup"; Description: "{cm:AutoStartProgram,{#MyAppName}}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Автозапуск ставится галочкой в мастере. Программа умеет включать и выключать
; его сама из настроек — ключ тот же, поэтому они не конфликтуют.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "Knack"; ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
