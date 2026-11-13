# client/signaling.py
"""WebSocket signaling transport for a VoiceEdge client."""

import json


async def send_json(websocket, message: dict) -> None:
    await websocket.send(json.dumps(message))


def decode_message(raw: str) -> dict:
    return json.loads(raw)
