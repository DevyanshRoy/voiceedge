# scripts/build_all.ps1
$ErrorActionPreference = "Stop"
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm client\voiceedge_client.spec
if ($LASTEXITCODE -ne 0) { throw "Client build failed." }
python -m PyInstaller --clean --noconfirm gateway\voiceedge_gateway.spec
if ($LASTEXITCODE -ne 0) { throw "Gateway build failed." }
Write-Host "Created dist\VoiceEdgeClient.exe and dist\VoiceEdgeGateway.exe"
