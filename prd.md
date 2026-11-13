# VoiceEdge Software PRD and Developer Guide

## 1. Purpose

VoiceEdge is a LAN-only voice system for two or more laptops. Every client
creates one WebRTC connection to the VoiceEdge gateway. The gateway receives
microphone media and relays it to the other clients in the same room. Clients
never establish a peer-to-peer media connection and no cloud service is used.

The Arduino console is optional. Removing the Arduino must not change client
or gateway behavior.

## 2. Current implementation

| Area | Implementation | Entry point |
|---|---|---|
| Signaling | WebSocket hello/offer/answer exchange | `gateway/signaling_server.py` |
| Media | Gateway-terminated aiortc connections and `MediaRelay` | `gateway/signaling_server.py` |
| Sessions | Room and active-session registry | `gateway/session_manager.py` |
| Audio input | 48 kHz mono, 20 ms, int16 sounddevice track | `client/audio_io.py` |
| Audio output | sounddevice output with a bounded queue | `client/audio_io.py` |
| Metrics | Calls, packets, bytes, latency, uptime, CPU, memory | `gateway/metrics_engine.py` |
| Lifecycle | Start, stop, restart, maintenance, snapshot | `gateway/controller.py` |
| Logging | Rotating file handler | `gateway/logger.py` |
| Discovery | UDP broadcast beacon on port 8766 | `gateway/main.py` |
| Arduino | Optional serial metrics and commands | `gateway/serial_bridge.py` |
| Plugins | Interface and failure-safe passthrough stub | `gateway/plugins/plugin_base.py` |
| Packaging | PyInstaller specs for client and gateway | `client/voiceedge_client.spec`, `gateway/voiceedge_gateway.spec` |

Semester 1 has no translation, AI, noise suppression, or real plugin.

## 3. Runtime topology

```text
Laptop B client ── WebSocket + WebRTC ──┐
                                        │
Laptop A gateway ── MediaRelay ─────────┤
                                        │
Laptop A client ── WebSocket + WebRTC ──┘
```

The WebSocket carries only signaling and status messages. Audio travels inside
the WebRTC connection between each client and the gateway.

## 4. Signaling flow

1. The client connects to `ws://GATEWAY_IP:8765`.
2. It sends `hello` with `version`, `client_id`, `name`, and `room`.
3. The gateway rejects an incompatible version, a stopped gateway, or a
   duplicate client ID.
4. The client creates one audio transceiver, attaches its microphone track,
   and sends an SDP `offer`.
5. The gateway creates one `RTCPeerConnection`, sets the offer, and returns an
   SDP `answer`.
6. When the gateway receives an audio track, it subscribes through
   `MediaRelay` and attaches that relay track to every other client in the
   room.
7. Disconnecting closes the peer connection, removes the relay track, and ends
   that client's sessions.

ICE is configured with an empty STUN/TURN list, so this is intended for local
LAN host candidates only.

## 5. Gateway operation

### Development mode

```powershell
.\scripts\setup_env.ps1
.\scripts\run_gateway.ps1 -Host 0.0.0.0 -Port 8765 -Serial off
```

The gateway monitor is enabled by default. Use `-NoMonitor` for a service-like
terminal. Monitor keys are:

* `s` start
* `x` stop
* `r` restart
* `m` toggle maintenance

Maintenance rejects new clients while existing connections remain alive.
Stopped gateways reject new clients.

### Packaged mode

Build both executables:

```powershell
.\scripts\build_all.ps1
```

Outputs:

* `dist\VoiceEdgeGateway.exe` — install/copy only this to Laptop A.
* `dist\VoiceEdgeClient.exe` — copy this to every client laptop.

For a normal user, start the host by double-clicking the gateway executable.
If Windows displays a firewall prompt, allow it on Private networks. If no
prompt appears, an administrator can run the firewall helper once:

```powershell
.\scripts\open_firewall.ps1 -GatewayExecutable .\dist\VoiceEdgeGateway.exe
```

Then the host executable can be opened directly:

```powershell
.\dist\VoiceEdgeGateway.exe --host 0.0.0.0 --port 8765 --serial off
```

The gateway executable is a console executable so its monitor and errors are
visible. The client executable is windowed and opens the Tk interface.

## 6. Firewall and network requirements

Windows Defender Firewall protects the laptop from inbound network traffic.
Run this in **Administrator PowerShell on the gateway laptop only**:

```powershell
.\scripts\open_firewall.ps1 -GatewayExecutable .\dist\VoiceEdgeGateway.exe
```

The script allows TCP 8765 for signaling, UDP 8766 for discovery, and the
gateway executable's UDP media traffic. Clients need outbound access only.
Both laptops must be on the same Wi-Fi and the access point must not enable
client isolation. A mobile hotspot is a useful diagnostic alternative.

Use `ipconfig` on the gateway laptop and give the client its Wi-Fi IPv4
address, for example `192.168.1.25:8765`.

## 7. Client behavior

The GUI stores the last gateway, name, room, microphone, and speaker in:

```text
%APPDATA%\VoiceEdge\client.json
```

The CLI is useful for development:

```powershell
python -m client.webrtc_client --cli --server 192.168.1.25:8765 --name B --room lab
python -m client.webrtc_client --list-devices
```

The client uses `sounddevice`, not `MediaPlayer`, DirectShow, or system
ffmpeg. The packaged client therefore does not require Python, pip, or ffmpeg.
Headphones are recommended to prevent acoustic feedback.

## 8. Serial protocol

Gateway to Arduino every second:

```text
M|<ON/OFF>|<calls>|<latency_ms>|<packets>|<plugin>|<NORMAL/MAINT>|<OK/HIGHLAT/FAULT>
```

Arduino to gateway:

```text
C|START
C|STOP
C|RESTART
C|MAINT
```

Serial is disabled by default. Use `--serial auto` or `--serial COM5` only
when an Arduino is connected. A missing or unplugged serial device is not a
gateway failure; the bridge retries silently with warnings in the log.

## 9. Metrics and logs

`MetricsEngine.snapshot()` returns active calls, latency, total packets, total
bytes, uptime, CPU, and memory. Relayed audio frames increment packet and byte
counters through `MeteredTrack`.

The rotating log is `voiceedge.log` in the current working directory. It is
the first place to inspect startup failures, serial errors, and unhandled
signaling errors.

## 10. How to fix common failures

### `pytest` or a command is blocked

Use the Python module form instead of the executable launcher:

```powershell
python -m pytest -q
python -m PyInstaller --version
```

Some managed Windows machines block `pytest.exe`, `pyinstaller.exe`, or newly
built unsigned executables through Application Control.

### Client cannot connect

1. Confirm the gateway process is running.
2. Run `ipconfig` on the gateway and use its Wi-Fi IPv4 address, not
   `127.0.0.1`.
3. Run the firewall script as Administrator.
4. Check that both devices are on the same network.
5. Try a mobile hotspot if the Wi-Fi uses client isolation.

### Client connects but there is no sound

Run `--list-devices`, select the correct devices, check Windows microphone
permissions, and use headphones. Do not start two clients using the same
exclusive microphone device during local testing.

### Version incompatibility

The protocol version is `VERSION = "1"` in
`client/webrtc_client.py` and `PROTOCOL_VERSION = "1"` in
`gateway/signaling_server.py`. Change and rebuild both sides together.

### Packaging failure

Run from the repository root. Delete only generated `build` and `dist`
directories if a stale build is suspected, then run:

```powershell
.\scripts\build_all.ps1
```

The specs collect aiortc, av, aioice, cryptography, websockets, sounddevice,
and serial dependencies. If Inno Setup is installed, create the optional
client installer with:

```powershell
iscc .\scripts\installer.iss
```

### Code change checklist

1. Keep the first line of every code file as its repository path comment.
2. Preserve the gateway-relay topology; never connect clients directly.
3. Use the existing session, metrics, controller, and serial helpers.
4. Add a focused test under `tests/`.
5. Run `python -m pytest -q` and `python -m compileall -q gateway client tests`.
6. Update this document and [README.md](README.md) when commands or behavior
   change.

## 11. Verification status

The repository currently passes five focused automated tests covering sessions,
relay callbacks, metrics, controller lifecycle, and serial parsing. Compilation
and a WebSocket hello/teardown smoke test also pass.

A clean-machine executable run, two physical laptops, Wi-Fi-drop reconnection,
and real microphone/speaker two-way audio require hardware or another laptop
and must be performed as a demo acceptance test.
