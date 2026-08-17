#define AppName "Local Runtime"
#define AppVersion GetEnv("RUNTIME_VERSION")

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\LocalRuntime
DefaultGroupName={#AppName}
OutputDir=..\..\dist
OutputBaseFilename=LocalRuntimeSetup-{#AppVersion}
; Per-user install: no admin for the install itself. The only UAC prompt in
; the whole experience is the scoped one for enabling WSL2.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\..\dist\LocalRuntime\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Local Runtime Setup"; Filename: "{app}\runtime.exe"; Parameters: "setup"

[Run]
Filename: "{app}\runtime.exe"; Parameters: "setup"; \
  Description: "Set up Local Runtime now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Destroys the VM and every project inside it before files are removed.
Filename: "{app}\runtime.exe"; Parameters: "uninstall --purge"; \
  Flags: runhidden; RunOnceId: "PurgeVm"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}"; Check: NeedsAddPath('{app}')

[Code]
function NeedsAddPath(Param: string): boolean;
var OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
  begin Result := True; exit; end;
  Result := Pos(';' + ExpandConstant(Param) + ';', ';' + OrigPath + ';') = 0;
end;
