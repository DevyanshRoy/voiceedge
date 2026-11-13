# gateway/controller.py
"""Single source of truth for gateway lifecycle and maintenance state."""

import asyncio
import time


class GatewayController:
    def __init__(self, metrics_engine=None):
        self.metrics_engine = metrics_engine
        self.running = False
        self.maintenance = False
        self.started_at = None
        self.fault = False

    def start(self):
        self.running = True
        self.started_at = self.started_at or time.time()

    def stop(self):
        self.running = False

    def restart(self):
        self.stop()
        self.start()

    def toggle_maintenance(self):
        self.maintenance = not self.maintenance
        return self.maintenance

    def snapshot(self):
        metrics = self.metrics_engine.snapshot() if self.metrics_engine else {
            "active_calls": 0, "latency_ms": 0, "total_packets": 0,
            "uptime_seconds": 0, "cpu_percent": 0, "memory_percent": 0,
        }
        health = "FAULT" if self.fault else ("HIGHLAT" if metrics["latency_ms"] > 150 else "OK")
        return {
            "gateway": "ON" if self.running else "OFF",
            "calls": metrics["active_calls"],
            "latency_ms": round(metrics["latency_ms"]),
            "packets": metrics["total_packets"],
            "plugin": "NONE",
            "mode": "MAINT" if self.maintenance else "NORMAL",
            "health": health,
            **metrics,
        }
