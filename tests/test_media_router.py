# tests/test_media_router.py
import unittest

from gateway.media_router import MediaRouter
from gateway.session_manager import SessionManager


class MediaRouterTests(unittest.TestCase):
    def test_routes_to_other_client(self):
        session = SessionManager().create_session("a", "b")
        delivered = []
        router = MediaRouter()
        router.create_route(session, lambda client, frame: delivered.append((client, frame)))
        self.assertTrue(router.route_frame(session.session_id, "a", b"frame"))
        self.assertEqual(delivered, [("b", b"frame")])