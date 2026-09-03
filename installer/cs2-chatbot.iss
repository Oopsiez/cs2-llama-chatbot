; Inno Setup script for the CS2 Chatbot installer.
;
; It wraps the single PyInstaller executable so the user gets the Windows install they expect:
; a Setup.exe, Start Menu and desktop shortcuts, and an entry in Add/Remove Programs. Nothing
; here needs Python on the target machine - the interpreter is inside the packaged exe.
;
; Build (on Windows, after scripts/build_exe.py has produced dist\CS2 Chatbot.exe):
;   iscc /DAppVersion=0.1.0 installer\cs2-chatbot.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "CS2 Chatbot"
#define AppPublisher "Oopsiez"
#define AppURL "https://github.com/Oopsiez/cs2-llama-chatbot"
#define AppExe "CS2 Chatbot.exe"

[Setup]
AppId={{7C0F2C7E-0B3E-4E9E-9A2E-2A0B2C6E9A11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, which is one less thing to explain.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=CS2 Chatbot Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} on GitHub"; Filename: "{#AppURL}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open the control panel now"; Flags: nowait postinstall skipifsilent
