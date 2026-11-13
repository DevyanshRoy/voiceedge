# client/voiceedge_client.spec
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
for package in ("aiortc", "av", "aioice", "sounddevice", "cryptography", "websockets"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["webrtc_client.py"], pathex=[".."], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, excludes=["tkinter.test"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="VoiceEdgeClient", console=False)
