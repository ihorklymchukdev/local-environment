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
; uninsdeletevalue only removes the whole Path value, never a single segment
; within it; NeedsAddPath below already avoids appending a duplicate, and the
; installed {app} segment is left behind on uninstall as a result.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}"; Check: NeedsAddPath('{app}'); Flags: uninsdeletevalue

[Code]
function NeedsAddPath(Param: string): boolean;
var OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
  begin Result := True; exit; end;
  Result := Pos(';' + ExpandConstant(Param) + ';', ';' + OrigPath + ';') = 0;
end;

function InitializeUninstall(): Boolean;
begin
  Result := MsgBox(
    'Uninstalling Local Runtime permanently deletes the VM and every ' +
    'project inside it. Project files live inside the VM, not on this ' +
    'PC, so nothing is recoverable afterward.' + #13#10#13#10 +
    'Continue with uninstall?',
    mbConfirmation, MB_YESNO) = IDYES;
end;
