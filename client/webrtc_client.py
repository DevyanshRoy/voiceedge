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
SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "VoiceEdge" / "client.json"


class VoiceEdgeClient:
    def __init__(self, server, name, room="lab", mic=None, speaker=None, status=None):
        self.server = server if server.startswith("ws://") else f"ws://{server}"
        self.name, self.room = name, room
        self.mic_device, self.speaker_device = mic, speaker
        self.on_status = status or (lambda _message: None)
        self.pc = None
        self.ws = None
        self.mic_track = None
        self.speaker = None
        self._stop = asyncio.Event()
        self.muted = False

    async def run(self):
        while not self._stop.is_set():
            try:
                self.on_status("Connecting")
                async with websockets.connect(self.server) as websocket:
                    self.ws = websocket
                    await self._send({
                        "type": "hello", "version": VERSION,
                        "client_id": self.name, "name": self.name, "room": self.room,
                    })
                    async for raw in websocket:
                        await self._handle(json.loads(raw))
            except (OSError, websockets.exceptions.WebSocketException) as exc:
                self.on_status(f"Error: {exc}")
                if self._stop.is_set():
                    break
                await asyncio.sleep(2)
            finally:
                await self._close_pc()

    async def _handle(self, message):
        kind = message.get("type")
        if kind == "ready":
            await self._make_offer()
        elif kind == "answer":
            await self.pc.setRemoteDescription(
                RTCSessionDescription(sdp=message["sdp"], type="answer")
            )
            names = message.get("session", {}).get("clients", [])
            peer = next((name for name in names if name != self.name), "room")
            self.on_status(f"In call with {peer}" if len(names) > 1 else "Waiting for another client")
        elif kind == "error":
            self.on_status(message.get("message", "Gateway error"))

    async def _make_offer(self):
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.mic_track = MicrophoneAudioTrack(self.mic_device)
        transceiver = self.pc.addTransceiver("audio", direction="sendrecv")
        transceiver.sender.replaceTrack(self.mic_track)
        self.mic_track.muted = self.muted

        @self.pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                self.speaker = SpeakerOutput(self.speaker_device)
                self.speaker.start(track)

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        await self._send({
            "type": "offer",
            "sdp": self.pc.localDescription.sdp,
        })

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
            await self._send({"type": "bye"})
            await self.ws.close()

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
    client = VoiceEdgeClient(args.server, args.name, args.room, args.mic, args.speaker)
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        pass


def gui_main():
    root = tk.Tk()
    root.title("VoiceEdge Client")
    frame = ttk.Frame(root, padding=12)
    frame.grid()
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
    devices = ["Default"]
    try:
        import sounddevice as sd
        devices = ["Default"] + [d["name"] for d in sd.query_devices()]
    except (OSError, ImportError):
        pass
    ttk.Label(frame, text="Mic").grid(row=6, column=0, sticky="w")
    mic = tk.StringVar(value=saved.get("mic", "Default"))
    ttk.Combobox(frame, textvariable=mic, values=devices, width=28).grid(row=6, column=1)
    ttk.Label(frame, text="Speaker").grid(row=7, column=0, sticky="w")
    speaker = tk.StringVar(value=saved.get("speaker", "Default"))
    ttk.Combobox(frame, textvariable=speaker, values=devices, width=28).grid(row=7, column=1)
    loop = asyncio.new_event_loop()
    client = None

    def connect():
        nonlocal client
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps({
            "server": fields["Gateway"].get(), "name": fields["Your name"].get(),
            "room": fields["Room"].get(), "mic": mic.get(), "speaker": speaker.get(),
        }), encoding="utf-8")
        client = VoiceEdgeClient(fields["Gateway"].get(), fields["Your name"].get(),
                                 fields["Room"].get(), None if mic.get() == "Default" else mic.get(),
                                 None if speaker.get() == "Default" else speaker.get(), status=status.set)
        threading.Thread(target=lambda: loop.run_until_complete(client.run()), daemon=True).start()

    def disconnect():
        if client:
            asyncio.run_coroutine_threadsafe(client.stop(), loop)
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
    ttk.Button(frame, text="Find gateway", command=find_gateway).grid(row=8, column=1)
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
