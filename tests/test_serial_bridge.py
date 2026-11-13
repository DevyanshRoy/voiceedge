# tests/test_serial_bridge.py
import unittest

from gateway.serial_bridge import format_metrics, parse_command


class SerialProtocolTests(unittest.TestCase):
    def test_protocol(self):
        line = format_metrics({
            "gateway": "ON", "calls": 1, "latency_ms": 20, "packets": 3,
            "plugin": "NONE", "mode": "NORMAL", "health": "OK",
        })
        self.assertEqual(line, "M|ON|1|20|3|NONE|NORMAL|OK\n")
        self.assertEqual(parse_command("C|MAINT"), "MAINT")
        self.assertIsNone(parse_command("C|UNKNOWN"))