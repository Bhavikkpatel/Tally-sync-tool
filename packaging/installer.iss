; Inno Setup script — product selected via env TALLY_SYNC_PRODUCT / defines
; Build with: ISCC packaging\installer.iss  (after PyInstaller)

#define MyAppVersion GetEnv("TALLY_SYNC_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.0.0"
#endif

#define Product GetEnv("TALLY_SYNC_PRODUCT")
#if Product == ""
  #define Product "pluschwood"
#endif

#if Product == "autosync"
  #define MyAppName "AutoSync Tally Sync"
  #define MyAppId "{{A7B1C2D3-E4F5-6789-ABCD-EF0123456789}"
  #define MyAppExeName "AutoSyncTallySync.exe"
  #define MyInstallDir "AutoSyncTallySync"
  #define MySetupBase "AutoSyncTallySyncSetup"
#else
  #define MyAppName "Pluschwood Tally Sync"
  #define MyAppId "{{8F3C2A71-9B44-4D1E-9C5A-A1B2C3D4E5F6}"
  #define MyAppExeName "PluschwoodTallySync.exe"
  #define MyInstallDir "PluschwoodTallySync"
  #define MySetupBase "PluschwoodTallySyncSetup"
#endif

#if Product == "autosync"
  #define MyAppPublisher "AutoSync"
  #define MyAppURL "https://autosync.app"
#else
  #define MyAppPublisher "Pluschwood"
  #define MyAppURL "https://console.pluschwood.com"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyInstallDir}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir=output
OutputBaseFilename={#MySetupBase}-{#MyAppVersion}
SetupIconFile=
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startupicon"; Description: "Start {#MyAppName} when I sign in to Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\{#MyInstallDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
