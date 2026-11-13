# tests/test_controller.py
import unittest

from gateway.controller import GatewayController


class ControllerTests(unittest.TestCase):
    def test_lifecycle_and_maintenance(self):
        controller = GatewayController()
        self.assertEqual(controller.snapshot()["gateway"], "OFF")
        controller.start()
        controller.toggle_maintenance()
        snapshot = controller.snapshot()
        self.assertEqual(snapshot["gateway"], "ON")
        self.assertEqual(snapshot["mode"], "MAINT")
        controller.stop()
        self.assertEqual(controller.snapshot()["gateway"], "OFF")
