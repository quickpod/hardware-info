; Inno Setup — HardwareInfo. Signed single-file installer, compiled in CI.
#define AppName "HardwareInfo"
#define AppVersion "1.0.8"

[Setup]
AppMutex=QuickOpen.HardwareInfo
AppId={{51A0F001-0009-4E5B-8C71-9B0E2F3A0009}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=QuickOpen (quickopen.ai)
AppPublisherURL=https://quickopen.ai/projects/hardware-info
DefaultDirName={autopf}\HardwareInfo
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\HardwareInfo.exe
OutputDir=dist
OutputBaseFilename=HardwareInfo-Setup
SetupIconFile=..\hardware-info.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=branding\wizard-large.bmp
WizardSmallImageFile=branding\wizard-small.bmp
AppCopyright=Apache-2.0. 100%% AI-built, published on QuickOpen (quickopen.ai).
VersionInfoCompany=QuickOpen
VersionInfoProductName=HardwareInfo
VersionInfoVersion=1.0.8.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=HardwareInfo is a 100%% AI-built, open-source offline tool, published on QuickOpen (quickopen.ai).%n%nThis will install it on your computer.
BeveledLabel=QuickOpen · quickopen.ai

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "trustca"; Description: "Trust the QuickOpen Root CA (lets Windows verify QuickOpen signatures)"; GroupDescription: "Security:"; Flags: unchecked

[Files]
Source: "staging\HardwareInfo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "staging\quickopen-root.crt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "staging\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme skipifsourcedoesntexist
Source: "staging\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\HardwareInfo"; Filename: "{app}\HardwareInfo.exe"; IconFilename: "{app}\HardwareInfo.exe"
Name: "{group}\Uninstall HardwareInfo"; Filename: "{uninstallexe}"
Name: "{autodesktop}\HardwareInfo"; Filename: "{app}\HardwareInfo.exe"; IconFilename: "{app}\HardwareInfo.exe"; Tasks: desktopicon

[Run]
Filename: "certutil.exe"; Parameters: "-addstore -user Root ""{app}\quickopen-root.crt"""; Tasks: trustca; Flags: runhidden; StatusMsg: "Trusting the QuickOpen Root CA..."
Filename: "{app}\HardwareInfo.exe"; Description: "Launch HardwareInfo now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\HardwareInfo"

