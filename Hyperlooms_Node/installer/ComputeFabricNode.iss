[Setup]
AppName=ComputeFabric Node
AppVersion=1.0.0
DefaultDirName={pf}\ComputeFabric Node
DefaultGroupName=ComputeFabric Node
OutputDir=..\dist
OutputBaseFilename=ComputeFabricNodeSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\ComputeFabricNode.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{userappdata}\ComputeFabric"
Name: "{userappdata}\ComputeFabric\logs"

[Icons]
Name: "{group}\ComputeFabric Node"; Filename: "{app}\ComputeFabricNode.exe"
Name: "{commondesktop}\ComputeFabric Node"; Filename: "{app}\ComputeFabricNode.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked
Name: "autostart"; Description: "Start ComputeFabric Node on login"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ComputeFabricNode"; ValueData: """{app}\ComputeFabricNode.exe"""; Tasks: autostart

[Run]
Filename: "{app}\ComputeFabricNode.exe"; Description: "Launch ComputeFabric Node"; Flags: nowait postinstall skipifsilent
