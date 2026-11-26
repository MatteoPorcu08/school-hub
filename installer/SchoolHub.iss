#ifndef AppVersion
  #define AppVersion "0.2.2"
#endif
[Setup]
AppId=SchoolHubRust.MatteoPorcu08
AppName=SchoolHub
AppVersion={#AppVersion}
AppPublisher=MatteoPorcu08
AppPublisherURL=https://github.com/MatteoPorcu08/school-hub
AppUpdatesURL=https://github.com/MatteoPorcu08/school-hub/releases
DefaultDirName={localappdata}\Programs\SchoolHub
DefaultGroupName=SchoolHub
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=SchoolHub-Setup
SetupIconFile=..\assets\schoolhub.ico
UninstallDisplayIcon={app}\SchoolHub.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; Flags: unchecked
[Files]
Source: "..\dist\SchoolHub.exe"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autoprograms}\SchoolHub"; Filename: "{app}\SchoolHub.exe"
Name: "{autodesktop}\SchoolHub"; Filename: "{app}\SchoolHub.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\SchoolHub.exe"; Description: "Avvia SchoolHub"; Flags: nowait postinstall skipifsilent
