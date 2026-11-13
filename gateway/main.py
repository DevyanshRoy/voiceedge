# gateway/main.py
"""VoiceEdge gateway entry point."""

import argparse
import asyncio
import json
import logging
import socket
import threading

from gateway.controller import GatewayController
from gateway.logger import configure_logging
from gateway.media_router import MediaRouter
from gateway.metrics_engine import MetricsEngine
from gateway.session_manager import SessionManager
from gateway.signaling_server import SignalingServer
from gateway.serial_bridge import SerialBridge
from gateway.monitor import run_monitor


async def discovery_beacon(host, port, stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        while not stop_event.is_set():
            payload = json.dumps({"name": "VoiceEdge Gateway", "ws_port": port}).encode()
            sock.sendto(payload, ("255.255.255.255", 8766))
            await asyncio.sleep(2)
    finally:
        sock.close()


async def async_main(args):
    configure_logging()
    sessions = SessionManager()
    router = MediaRouter()
    metrics = MetricsEngine(sessions, router)
    controller = GatewayController(metrics)
    controller.start()
    monitor_thread = None
    if not args.no_monitor:
        monitor_thread = threading.Thread(target=run_monitor, args=(controller,), daemon=True)
        monitor_thread.start()
    server = SignalingServer(
        sessions, router, args.host, args.port,
        gateway_enabled=lambda: controller.running and not controller.maintenance,
        metrics_engine=metrics,
    )
    bridge = None
    if args.serial != "off":
        bridge = SerialBridge(controller.snapshot, lambda command: _handle_command(controller, command),
                              None if args.serial == "auto" else args.serial)
        bridge.start()
    stop_event = asyncio.Event()
    beacon = asyncio.create_task(discovery_beacon(args.host, args.port, stop_event))
    server_task = asyncio.create_task(server.start())
    try:
        await server_task
    finally:
        stop_event.set()
        await server.stop()
        if bridge:
            bridge.stop()
        beacon.cancel()


def _handle_command(controller, command):
    if command == "START":
        controller.start()
    elif command == "STOP":
        controller.stop()
    elif command == "RESTART":
        controller.restart()
    elif command == "MAINT":
        controller.toggle_maintenance()


def main():
    parser = argparse.ArgumentParser(description="VoiceEdge gateway")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--serial", default="off", help="off, auto, or COM port")
    parser.add_argument("--no-monitor", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Gateway stopped")


if __name__ == "__main__":
    main()