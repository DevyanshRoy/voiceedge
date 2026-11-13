# gateway/signaling_server.py
"""Gateway-terminated WebRTC signaling and media relay."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import AudioStreamTrack
import websockets

from gateway.media_router import MediaRouter
from gateway.session_manager import SessionManager

log = logging.getLogger("voiceedge.signaling")
PROTOCOL_VERSION = "1"


@dataclass
class ClientConnection:
    client_id: str
    name: str
    room: str
    websocket: Any
    pc: RTCPeerConnection | None = None
    tracks: list[Any] = field(default_factory=list)


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
        self._relay = MediaRelay()

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
        pc.addTransceiver("audio", direction="sendrecv")
        for other in self._room_clients(connection.room):
            if other.client_id != connection.client_id:
                for track in self.media_router.tracks_for(
                    [other.client_id], ""
                ):
                    pc.addTrack(MeteredTrack(track, self.metrics_engine) if self.metrics_engine else track)

        @pc.on("track")
        def on_track(track):
            if track.kind != "audio":
                return
            relay_track = self._relay.subscribe(track)
            connection.tracks.append(relay_track)
            self.media_router.register_track(connection.client_id, relay_track)
            for other in self._room_clients(connection.room):
                if other.client_id != connection.client_id and other.pc:
                    other.pc.addTrack(
                        MeteredTrack(relay_track, self.metrics_engine)
                        if self.metrics_engine else relay_track
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

    def _room_clients(self, room: str) -> list[ClientConnection]:
        return [client for client in self.clients.values() if client.room == room]

    def _room_status(self, room: str) -> dict:
        clients = self._room_clients(room)
        return {"clients": [client.name for client in clients]}

    async def _disconnect(self, connection: ClientConnection) -> None:
        if self.clients.get(connection.client_id) is not connection:
            return
        self.clients.pop(connection.client_id, None)
        self.media_router.unregister_track(connection.client_id)
        self.session_manager.end_sessions_for_client(connection.client_id)
        if connection.pc and connection.pc.connectionState != "closed":
            await connection.pc.close()

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
