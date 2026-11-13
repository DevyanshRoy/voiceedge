; scripts/installer.iss
[Setup]
AppName=VoiceEdge Client
AppVersion=1.0
DefaultDirName={autopf}\VoiceEdge Client
OutputBaseFilename=VoiceEdgeClient-Setup

[Files]
Source: "dist\VoiceEdgeClient.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\VoiceEdge Client"; Filename: "{app}\VoiceEdgeClient.exe"
