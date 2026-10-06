; Instalador de E-Ink Assistant (Inno Setup 6). Se compila desde build_release.ps1:
;   ISCC.exe /DAppVersion=1.0.0 packaging\installer.iss
; Instala por usuario (sin permisos de administrador) en %LOCALAPPDATA%\Programs.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "E-Ink Assistant"
#define AppExe "EInkAssistant.exe"

[Setup]
AppId={{7B2E4C61-3F0A-4D8E-9A51-EB1C2D7F4A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=eink-assistant
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\out\release
OutputBaseFilename=EInkAssistant-Setup-{#AppVersion}
SetupIconFile=..\out\build\eink-assistant.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"
Name: "startup"; Description: "Iniciar con Windows (en la bandeja del sistema)"
Name: "claude"; Description: "Conectar con Claude Desktop (para que Claude pueda escribir en la pantalla)"; Flags: unchecked

[Files]
Source: "..\out\dist\EInkAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; Mismo nombre que el que crea el programa (ui/startup.py), así la casilla
; «Iniciar con Windows» de la ventana lo reconoce y lo puede quitar.
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--minimized"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--register-mcp"; StatusMsg: "Conectando con Claude Desktop..."; Tasks: claude
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "CloseApp"

[UninstallDelete]
; Accesos directos que el programa puede haber creado por su cuenta.
Type: files; Name: "{userstartup}\{#AppName}.lnk"
Type: files; Name: "{userdesktop}\{#AppName}.lnk"
