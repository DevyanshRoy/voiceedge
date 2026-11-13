# VoiceEdge

VoiceEdge is a local Wi-Fi voice system. The gateway laptop is the central
meeting point: every microphone stream goes **client → gateway → client**.
Clients never connect directly to each other, and no internet service is
required.

Read [prd.md](prd.md) for the full architecture and repair guide. The original
academic requirements remain in
[Major-Project-PRD.md](Major-Project-PRD.md).

Normal users should start with the simple [User.md](User.md) guide.

## Fastest demo

### 1. Build the two programs

From the repository root:

```powershell
.\scripts\build_all.ps1
```

This creates:

```text
dist\VoiceEdgeGateway.exe
dist\VoiceEdgeClient.exe
```

Copy `VoiceEdgeGateway.exe` to the host laptop and `VoiceEdgeClient.exe` to
each other laptop. No Python, pip, ffmpeg, or Arduino is required on the
client laptop.

### 2. Start the gateway laptop

Normally, simply double-click `VoiceEdgeGateway.exe`. Windows may show a
firewall prompt; choose **Allow access** on Private networks.

If Windows does not show that prompt, run this one-time repair command from
Administrator PowerShell in the repository folder:

```powershell
.\scripts\open_firewall.ps1 -GatewayExecutable .\dist\VoiceEdgeGateway.exe
```

The firewall is Windows Defender Firewall. It controls whether other laptops
may open connections to this laptop. VoiceEdge needs TCP `8765` for signaling
and UDP `8766` for gateway discovery. Clients only need outbound access.

The normal daily startup is just:

```powershell
.\dist\VoiceEdgeGateway.exe --host 0.0.0.0 --port 8765 --serial off
```

Find the host Wi-Fi address:

```powershell
ipconfig
```

Use the **IPv4 Address** from the Wi-Fi adapter, such as `192.168.1.25`.

### 3. Start a client

Double-click `VoiceEdgeClient.exe` on the other laptop. Enter
`192.168.1.25:8765`, or click **Find gateway**, then click **Connect**.
Choose the room `lab`, select audio devices, and use headphones.

## Developer setup

```powershell
.\scripts\setup_env.ps1
python -m pytest -q
python -m compileall -q gateway client tests
```

For development, run the Python programs instead of the executables:

```powershell
.\scripts\run_gateway.ps1
.\scripts\run_client.ps1 -Server 127.0.0.1:8765 -Name LaptopA
```

The CLI client can list audio devices:

```powershell
python -m client.webrtc_client --list-devices
```

Use `--cli` for a second local client. Two local clients may compete for one
microphone, so separate microphones or a second laptop is more reliable.

## Repository map

* [gateway/main.py](gateway/main.py): starts the gateway, discovery, metrics,
  monitor, and optional serial bridge.
* [gateway/signaling_server.py](gateway/signaling_server.py): validates hello
  messages, performs WebRTC signaling, and relays audio through `MediaRelay`.
* [gateway/session_manager.py](gateway/session_manager.py): active room calls.
* [gateway/media_router.py](gateway/media_router.py): legacy frame-route API
  plus relay-track registry.
* [gateway/metrics_engine.py](gateway/metrics_engine.py): traffic and system
  metrics.
* [gateway/controller.py](gateway/controller.py): lifecycle single source of
  truth.
* [gateway/serial_bridge.py](gateway/serial_bridge.py): optional Arduino link.
* [client/webrtc_client.py](client/webrtc_client.py): GUI, CLI, signaling, and
  one client-side WebRTC connection.
* [client/audio_io.py](client/audio_io.py): sounddevice microphone track and
  speaker output.
* [gateway/plugins/plugin_base.py](gateway/plugins/plugin_base.py): Semester 1
  plugin interface only.

## Gateway controls

The terminal monitor supports:

| Key | Action |
|---|---|
| `s` | Start |
| `x` | Stop accepting new sessions |
| `r` | Restart |
| `m` | Toggle maintenance |

Maintenance rejects new calls but keeps existing calls. Serial commands use
the same controller. Arduino is optional and disabled by default with
`--serial off`.

## Arduino wiring

| Part | Pins |
|---|---|
| OLED I2C | SDA A4, SCL A5 |
| LEDs | Green D4, Blue D5, Yellow D6, Red D7 |
| Buttons | Start D8, Stop D9, Restart D10, Maintenance D11 |

See [docs/serial-protocol.md](docs/serial-protocol.md) and
[embedded/voiceedge_console/voiceedge_console.ino](embedded/voiceedge_console/voiceedge_console.ino).

## Troubleshooting

* **Access denied running firewall script:** use Administrator PowerShell.
* **Wrong address:** use the gateway laptop's Wi-Fi IPv4 address, never
  `localhost` or `127.0.0.1` from another laptop.
* **No connection:** check firewall rules, same Wi-Fi, and Wi-Fi client
  isolation. A mobile hotspot is a useful test.
* **No audio:** run `--list-devices`, choose the correct devices, check
  Windows microphone permissions, and use headphones.
* **Version error:** rebuild gateway and client together; both currently use
  protocol version `1`.
* **Build launcher blocked by Windows:** use `python -m pytest` and
  `python -m PyInstaller` rather than `pytest.exe` or `pyinstaller.exe`.
* **SmartScreen warning:** the unsigned executable may show **More info →
  Run anyway**.

For detailed recovery steps and implementation rules, see [prd.md](prd.md).
