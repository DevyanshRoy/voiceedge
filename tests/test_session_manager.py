# tests/test_session_manager.py
import unittest

from gateway.session_manager import SessionManager


class SessionManagerTests(unittest.TestCase):
    def test_create_and_end(self):
        manager = SessionManager()
        session = manager.create_session("a", "b", "lab")
        self.assertEqual(manager.active_call_count(), 1)
        self.assertEqual(session.room, "lab")
        self.assertTrue(manager.end_session(session.session_id))
        self.assertEqual(manager.active_call_count(), 0)