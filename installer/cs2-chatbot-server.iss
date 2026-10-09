; Inno Setup script for the CS2 Chatbot *server* installer: turns a spare Windows PC on the LAN
; into the bot's brain. It installs Ollama (if missing), opens it to the private network with a
; firewall rule, and pulls the chat model - all from installer\server\install.ps1.
;
; Build: iscc /DAppVersion=1.0.0 installer\cs2-chatbot-server.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "CS2 Chatbot Server"
#define AppURL "https://github.com/Oopsiez/cs2-llama-chatbot"

[Setup]
AppId={{3B6D4F1A-5C2E-4B7A-9D8E-6F1A2B3C4D5E}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Oopsiez
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
; Firewall rules and machine-wide environment need an elevated installer.
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=CS2 Chatbot Server Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "server\install.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "server\uninstall.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "server\panel.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\panel.ps1"""; \
  Comment: "Switch the AI models on or off and see who is connected"
Name: "{autodesktop}\{#AppName}"; Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\panel.ps1"""; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Put a CS2 Chatbot Server shortcut on the desktop"; Flags: unchecked

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -NoExit -File ""{app}\install.ps1"""; \
  Description: "Install Ollama, open the firewall and pull the model"; Flags: postinstall runascurrentuser waituntilterminated
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\panel.ps1"""; \
  Description: "Open the server window"; Flags: postinstall nowait runascurrentuser

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "firewall"
