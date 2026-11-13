# scripts/build_client.ps1
$ErrorActionPreference = "Stop"
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm client\voiceedge_client.spec
if ($LASTEXITCODE -ne 0) { throw "Client build failed." }
