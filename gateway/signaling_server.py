# gateway/signaling_server.py
"""Gateway-terminated WebRTC signaling and media relay."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

import av
import numpy as np
from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError
import websockets

from gateway.media_router import MediaRouter
from gateway.session_manager import SessionManager

log = logging.getLogger("voiceedge.signaling")
PROTOCOL_VERSION = "1"


# gateway/signaling_server.py  (replace GatewayRelayTrack)
class GatewayRelayTrack(AudioStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self._queue = asyncio.Queue(maxsize=50)
        self._pts = 0
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)

    def put_frame(self, frame):
        try:
            frames = self._resampler.resample(frame)
        except Exception:
            return
        for f in frames:
            try:
                self._queue.put_nowait(f)
            except asyncio.QueueFull:
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(f)
                except Exception:
                    pass

    async def recv(self):
        try:
            frame = await asyncio.wait_for(self._queue.get(), timeout=0.04)
        except asyncio.TimeoutError:
            frame = av.AudioFrame.from_ndarray(
                np.zeros((1, 960), dtype=np.int16), format="s16", layout="mono"
            )
            frame.sample_rate = 48000
        frame.pts = self._pts
        frame.time_base = Fraction(1, 48000)
        self._pts += frame.samples
        return frame
        
@dataclass
class ClientConnection:
    client_id: str
    name: str
    room: str
    websocket: Any
    pc: RTCPeerConnection | None = None
    relay_track: GatewayRelayTrack | None = None
    forward_task: asyncio.Task | None = None


class MeteredTrack(AudioStreamTrack):
    def __init__(self, source, metrics):
        super().__init__()
        self.source = source
        self.metrics = metrics

    async def recv(self):
        frame = await self.source.recv()
        self.metrics.record_routed_frame(frame.samples * 2)
        return frame


class SignalingServer:
    def __init__(
        self,
        session_manager: SessionManager,
        media_router: MediaRouter | None = None,
        host: str = "0.0.0.0",
        port: int = 8765,
        version: str = PROTOCOL_VERSION,
        gateway_enabled=None,
        metrics_engine=None,
    ):
        self.session_manager = session_manager
        self.media_router = media_router or MediaRouter()
        self.host, self.port, self.version = host, port, version
        self.gateway_enabled = gateway_enabled or (lambda: True)
        self.metrics_engine = metrics_engine
        self.clients: dict[str, ClientConnection] = {}
        self._server = None

    async def handler(self, websocket):
        connection: ClientConnection | None = None
        try:
            async for raw in websocket:
                message = json.loads(raw)
                kind = message.get("type")
                if kind == "hello":
                    connection = await self._hello(websocket, message)
                elif connection and kind == "offer":
                    await self._offer(connection, message)
                elif connection and kind == "bye":
                    break
                else:
                    await self._send(websocket, {"type": "error", "message": "Send hello first."})
        except (json.JSONDecodeError, websockets.exceptions.ConnectionClosed):
            pass
        except Exception:
            log.exception("Unhandled signaling error")
            if connection:
                await self._send(connection.websocket, {"type": "error", "message": "Gateway error."})
        finally:
            if connection:
                await self._disconnect(connection)

    async def _hello(self, websocket, message: dict) -> ClientConnection | None:
        if message.get("version") != self.version:
            await self._send(websocket, {
                "type": "error",
                "code": "INCOMPATIBLE_VERSION",
                "message": f"Incompatible client version; gateway requires {self.version}.",
            })
            return None
        if not self.gateway_enabled():
            await self._send(websocket, {"type": "error", "code": "GATEWAY_STOPPED", "message": "Gateway is stopped."})
            return None
        client_id = str(message.get("client_id", "")).strip()
        if not client_id or client_id in self.clients:
            await self._send(websocket, {"type": "error", "message": "Client name is missing or already in use."})
            return None
        connection = ClientConnection(
            client_id=client_id,
            name=str(message.get("name") or client_id),
            room=str(message.get("room") or "lab"),
            websocket=websocket,
        )
        self.clients[client_id] = connection
        room_clients = self._room_clients(connection.room)
        if len(room_clients) >= 2:
            self.session_manager.create_session(
                room_clients[-2].client_id, room_clients[-1].client_id, connection.room
            )
        await self._send(websocket, {"type": "ready", "room": connection.room})
        return connection

    async def _offer(self, connection: ClientConnection, message: dict) -> None:
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        connection.pc = pc
        connection.relay_track = GatewayRelayTrack()
        track_to_send = (
            MeteredTrack(connection.relay_track, self.metrics_engine)
            if self.metrics_engine
            else connection.relay_track
        )
        pc.addTrack(track_to_send)

        @pc.on("track")
        def on_track(track):
            if track.kind != "audio":
                return
            log.info("Gateway received audio track from %s", connection.client_id)
            connection.forward_task = asyncio.create_task(
                self._forward_audio(connection, track)
            )

        @pc.on("connectionstatechange")
        async def on_state_change():
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                await self._disconnect(connection)

        await pc.setRemoteDescription(RTCSessionDescription(
            sdp=message["sdp"], type="offer"
        ))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await self._send(connection.websocket, {
            "type": "answer",
            "sdp": pc.localDescription.sdp,
            "session": self._room_status(connection.room),
        })
        for other in self._room_clients(connection.room):
            if other.client_id != connection.client_id:
                try:
                    await self._send(other.websocket, {
                        "type": "session_update",
                        "session": self._room_status(connection.room),
                    })
                except Exception:
                    pass

    async def _forward_audio(self, sender: ClientConnection, track: AudioStreamTrack):
        try:
            while True:
                frame = await track.recv()
                for other in self._room_clients(sender.room):
                    if other.client_id != sender.client_id and other.relay_track:
                        other.relay_track.put_frame(frame)
        except (MediaStreamError, asyncio.CancelledError):
            pass
        except Exception:
            log.exception("Error in gateway audio forwarder for %s", sender.client_id)

    def _room_clients(self, room: str) -> list[ClientConnection]:
        return [client for client in self.clients.values() if client.room == room]

    def _room_status(self, room: str) -> dict:
        clients = self._room_clients(room)
        return {"clients": [client.name for client in clients]}

    async def _disconnect(self, connection: ClientConnection) -> None:
        if self.clients.get(connection.client_id) is not connection:
            return
        self.clients.pop(connection.client_id, None)
        if connection.forward_task:
            connection.forward_task.cancel()
            connection.forward_task = None
        self.session_manager.end_sessions_for_client(connection.client_id)
        if connection.pc and connection.pc.connectionState != "closed":
            await connection.pc.close()
        for other in self._room_clients(connection.room):
            try:
                await self._send(other.websocket, {
                    "type": "session_update",
                    "session": self._room_status(connection.room),
                })
            except Exception:
                pass
        if connection.pc and connection.pc.connectionState != "closed":
            await connection.pc.close()
        for other in self._room_clients(connection.room):
            try:
                await self._send(other.websocket, {
                    "type": "session_update",
                    "session": self._room_status(connection.room),
                })
            except Exception:
                pass

    async def _send(self, websocket, message: dict) -> None:
        await websocket.send(json.dumps(message))

    async def start(self):
        self._server = await websockets.serve(self.handler, self.host, self.port)
        log.info("Signaling server listening on ws://%s:%s", self.host, self.port)
        await asyncio.Future()

    async def stop(self):
        for client in list(self.clients.values()):
            await self._disconnect(client)
        if self._server:
            self._server.close()
            await self._server.wait_closed()
