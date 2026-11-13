# tests/test_metrics_engine.py
import unittest

from gateway.media_router import MediaRouter
from gateway.metrics_engine import MetricsEngine
from gateway.session_manager import SessionManager


class MetricsTests(unittest.TestCase):
    def test_records_traffic(self):
        engine = MetricsEngine(SessionManager(), MediaRouter())
        engine.record_routed_frame(10, 25)
        snapshot = engine.snapshot()
        self.assertEqual(snapshot["total_packets"], 1)
        self.assertEqual(snapshot["latency_ms"], 25)