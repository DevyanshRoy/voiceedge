# client/webrtc_client.py
"""VoiceEdge gateway-relayed WebRTC client, CLI, and small Tk GUI."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import socket
import threading
import tkinter as tk
from tkinter import ttk

import websockets
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription

from client.audio_io import MicrophoneAudioTrack, SpeakerOutput

log = logging.getLogger("voiceedge.client")
VERSION = "1"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "VoiceEdge"
APP_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_PATH = APP_DIR / "client.json"
CLIENT_LOG_PATH = APP_DIR / "client.log"

try:
    logging.basicConfig(
        filename=str(CLIENT_LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
        encoding="utf-8",
    )
except Exception:
    pass


class VoiceEdgeClient:
    def __init__(self, server, name, room="lab", mic=None, speaker=None, status=None, muted=False):
        self.server = server if server.startswith("ws://") else f"ws://{server}"
        self.name, self.room = name, room
        self.mic_device, self.speaker_device = mic, speaker
        self.on_status = status or (lambda _message: None)
        self.pc = None
        self.ws = None
        self.mic_track = None
        self.speaker = None
        self._stop = asyncio.Event()
        self.muted = muted

    async def run(self):
        connected = False
        log.info("Starting connection to server=%s client_id=%s room=%s", self.server, self.name, self.room)
        try:
            self.on_status("Connecting...")
            async with websockets.connect(self.server, open_timeout=4) as websocket:
                self.ws = websocket
                connected = True
                log.info("WebSocket connected to %s", self.server)
                self.on_status("Connected")
                await self._send({
                    "type": "hello", "version": VERSION,
                    "client_id": self.name, "name": self.name, "room": self.room,
                })
                async for raw in websocket:
                    if self._stop.is_set():
                        break
                    await self._handle(json.loads(raw))
        except asyncio.CancelledError:
            log.info("Connection task cancelled")
        except (OSError, websockets.exceptions.WebSocketException, TimeoutError) as exc:
            log.warning("Connection failed to %s: %s", self.server, exc)
            if not self._stop.is_set():
                if not connected:
                    self.on_status(f"Not able to connect ({type(exc).__name__})")
                else:
                    self.on_status("Disconnected")
        finally:
            await self._close_pc()
            if self._stop.is_set():
                self.on_status("Disconnected")

    async def _handle(self, message):
        try:
            kind = message.get("type")
            log.info("Received signaling message: %s", kind)
            if kind == "ready":
                await self._make_offer()
            elif kind == "answer":
                await self.pc.setRemoteDescription(
                    RTCSessionDescription(sdp=message["sdp"], type="answer")
                )
                names = message.get("session", {}).get("clients", [])
                peer = next((name for name in names if name != self.name), "room")
                log.info("Active participants in room '%s': %s", self.room, names)
                self.on_status(f"Connected: In call with {peer}" if len(names) > 1 else "Connected: Waiting for another client")
            elif kind == "session_update":
                names = message.get("session", {}).get("clients", [])
                peer = next((name for name in names if name != self.name), "room")
                log.info("Session update in room '%s': %s", self.room, names)
                self.on_status(f"Connected: In call with {peer}" if len(names) > 1 else "Connected: Waiting for another client")
            elif kind == "error":
                log.error("Gateway error: %s", message.get("message"))
                self.on_status(message.get("message", "Gateway error"))
        except Exception as exc:
            log.exception("Error handling signaling message: %s", exc)

    async def _make_offer(self):
        try:
            self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            self.mic_track = MicrophoneAudioTrack(self.mic_device)
            self.pc.addTrack(self.mic_track)
            self.mic_track.muted = self.muted

            @self.pc.on("track")
            def on_track(track):
                if track.kind == "audio":
                    log.info("Received incoming audio track from peer")
                    self.speaker = SpeakerOutput(self.speaker_device)
                    self.speaker.start(track)

            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            await self._send({
                "type": "offer",
                "sdp": self.pc.localDescription.sdp,
            })
            log.info("Sent WebRTC offer to gateway")
        except Exception as exc:
            log.exception("Error making WebRTC offer: %s", exc)

    async def _send(self, message):
        await self.ws.send(json.dumps(message))

    async def _close_pc(self):
        if self.mic_track:
            self.mic_track.stop()
            self.mic_track = None
        if self.speaker:
            self.speaker.stop()
            self.speaker = None
        if self.pc:
            await self.pc.close()
            self.pc = None

    async def stop(self):
        self._stop.set()
        if self.ws:
            try:
                await self._send({"type": "bye"})
                await self.ws.close()
            except Exception:
                pass
        await self._close_pc()

    def set_muted(self, muted):
        self.muted = muted
        if self.mic_track:
            self.mic_track.muted = muted


def list_devices():
    import sounddevice as sd
    for index, device in enumerate(sd.query_devices()):
        print(f"{index}: {device['name']} (in={device['max_input_channels']}, out={device['max_output_channels']})")


def cli_main(args):
    if args.list_devices:
        list_devices()
        return
    client = VoiceEdgeClient(args.server, args.name, args.room, args.mic, args.speaker, status=print)
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        pass


class TkLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            self.callback(self.format(record))
        except Exception:
            pass


def gui_main():
    root = tk.Tk()
    root.title("VoiceEdge Client")
    frame = ttk.Frame(root, padding=12)
    frame.grid(sticky="nsew")
    fields = {}
    saved = {}
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
    for row, (label, default) in enumerate((("Gateway", saved.get("server", "127.0.0.1:8765")),
                                             ("Your name", saved.get("name", socket.gethostname())),
                                             ("Room", saved.get("room", "lab")))):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        value = tk.StringVar(value=default)
        ttk.Entry(frame, textvariable=value, width=30).grid(row=row, column=1)
        fields[label] = value
    status = tk.StringVar(value="Disconnected")
    ttk.Label(frame, textvariable=status).grid(row=4, column=0, columnspan=2)
    input_devices = ["Default"]
    output_devices = ["Default"]
    try:
        import sounddevice as sd
        for d in sd.query_devices():
            name = d.get("name", "")
            if d.get("max_input_channels", 0) > 0 and name not in input_devices:
                input_devices.append(name)
            if d.get("max_output_channels", 0) > 0 and name not in output_devices:
                output_devices.append(name)
    except Exception:
        pass
    ttk.Label(frame, text="Mic").grid(row=6, column=0, sticky="w")
    mic = tk.StringVar(value=saved.get("mic", "Default"))
    ttk.Combobox(frame, textvariable=mic, values=input_devices, width=28).grid(row=6, column=1)
    ttk.Label(frame, text="Speaker").grid(row=7, column=0, sticky="w")
    speaker = tk.StringVar(value=saved.get("speaker", "Default"))
    ttk.Combobox(frame, textvariable=speaker, values=output_devices, width=28).grid(row=7, column=1)
    client = None
    client_loop = None

    def disconnect():
        nonlocal client, client_loop
        if client and client_loop and client_loop.is_running():
            asyncio.run_coroutine_threadsafe(client.stop(), client_loop)
        status.set("Disconnected")

    def connect():
        nonlocal client, client_loop
        disconnect()
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps({
            "server": fields["Gateway"].get(), "name": fields["Your name"].get(),
            "room": fields["Room"].get(), "mic": mic.get(), "speaker": speaker.get(),
        }), encoding="utf-8")
        client = VoiceEdgeClient(fields["Gateway"].get(), fields["Your name"].get(),
                                 fields["Room"].get(), None if mic.get() == "Default" else mic.get(),
                                 None if speaker.get() == "Default" else speaker.get(), status=status.set,
                                 muted=muted.get())
        def run_thread():
            nonlocal client_loop
            client_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(client_loop)
            try:
                client_loop.run_until_complete(client.run())
            finally:
                client_loop.close()

        threading.Thread(target=run_thread, daemon=True).start()
    ttk.Button(frame, text="Connect", command=connect).grid(row=3, column=0)
    ttk.Button(frame, text="Disconnect", command=disconnect).grid(row=3, column=1)
    muted = tk.BooleanVar()
    ttk.Checkbutton(frame, text="Mute", variable=muted,
                    command=lambda: client and client.set_muted(muted.get())).grid(row=8, column=0)
    def find_gateway():
        def listen():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.5)
            try:
                sock.bind(("", 8766))
                data, address = sock.recvfrom(1024)
                beacon = json.loads(data.decode())
                root.after(0, lambda: fields["Gateway"].set(f"{address[0]}:{beacon['ws_port']}"))
            except (OSError, ValueError, KeyError):
                root.after(0, lambda: status.set("Gateway not found"))
            finally:
                sock.close()
        threading.Thread(target=listen, daemon=True).start()

    log_frame = ttk.Frame(frame)
    log_text = tk.Text(log_frame, height=8, width=42, wrap="word", bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 8))
    log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.pack(side="left", fill="both", expand=True)
    log_scroll.pack(side="right", fill="y")
    log_visible = False

    def append_log(msg):
        def _insert():
            log_text.insert("end", msg + "\n")
            log_text.see("end")
        root.after(0, _insert)

    ui_handler = TkLogHandler(append_log)
    ui_handler.setFormatter(logging.Formatter("%(asctime)s: %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(ui_handler)

    if CLIENT_LOG_PATH.exists():
        try:
            lines = CLIENT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-25:]
            for line in lines:
                log_text.insert("end", line + "\n")
            log_text.see("end")
        except Exception:
            pass

    def toggle_logs():
        nonlocal log_visible
        log_visible = not log_visible
        if log_visible:
            log_frame.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
            log_btn.configure(text="Logs ▲")
        else:
            log_frame.grid_remove()
            log_btn.configure(text="Logs ▼")

    btn_row = ttk.Frame(frame)
    btn_row.grid(row=8, column=1, sticky="w")
    ttk.Button(btn_row, text="Find gateway", command=find_gateway).pack(side="left", padx=2)
    log_btn = ttk.Button(btn_row, text="Logs ▼", command=toggle_logs)
    log_btn.pack(side="left", padx=2)
    ttk.Label(frame, text="Headphones recommended").grid(row=5, column=0, columnspan=2)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="VoiceEdge client")
    parser.add_argument("--server", default="127.0.0.1:8765")
    parser.add_argument("--name", default=socket.gethostname())
    parser.add_argument("--room", default="lab")
    parser.add_argument("--mic")
    parser.add_argument("--speaker")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--cli", action="store_true")
    args = parser.parse_args()
    if args.cli or args.list_devices:
        cli_main(args)
    else:
        gui_main()


if __name__ == "__main__":
    main()
