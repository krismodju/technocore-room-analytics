"""
Tests for event_query_client.

Run with: python -m unittest analytics/event_query_client_test.py
or:       pytest analytics/event_query_client_test.py

These tests use only the standard library (unittest, urllib, json) and
fake the HTTP transport via urllib's opener patching, so they require
no external dependencies and no live server.
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from analytics.event_query_client import (
    EventQueryClient,
    EventQueryError,
    RoomEventsQuery,
)


def _fake_response(payload, status=200):
    """Build a mock object that mimics urllib's response interface."""
    body = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestEventQueryClient(unittest.TestCase):
    def setUp(self):
        self.client = EventQueryClient(base_url="https://api.example.test")

    def test_build_url_uses_default_room_id(self):
        url = self.client._build_url("/r/events", {"limit": 10})
        self.assertEqual(url, "https://api.example.test/r/events?limit=10")

    def test_room_events_query_to_params_includes_filters(self):
        q = RoomEventsQuery(
            room_id="r-123",
            event_type="message",
            since="2024-01-01T00:00:00Z",
            until="2024-01-02T00:00:00Z",
            actor_did="did:key:abc",
            limit=50,
            cursor="opaque-cursor",
        )
        params = q.to_params()
        self.assertEqual(params["room_id"], "r-123")
        self.assertEqual(params["type"], "message")
        self.assertEqual(params["since"], "2024-01-01T00:00:00Z")
        self.assertEqual(params["actor"], "did:key:abc")
        self.assertEqual(params["limit"], 50)
        self.assertEqual(params["cursor"], "opaque-cursor")

    def test_room_events_query_omits_blank_fields(self):
        q = RoomEventsQuery(room_id="r-1", limit=5)
        params = q.to_params()
        self.assertNotIn("since", params)
        self.assertNotIn("until", params)
        self.assertNotIn("actor", params)
        self.assertNotIn("cursor", params)
        self.assertEqual(params["room_id"], "r-1")
        self.assertEqual(params["limit"], 5)

    def test_list_room_events_parses_payload(self):
        payload = {
            "events": [
                {"id": "e1", "type": "message", "ts": "2024-01-01T00:00:00Z"},
                {"id": "e2", "type": "join", "ts": "2024-01-01T00:01:00Z"},
            ],
            "next_cursor": "c-2",
        }
        with patch.object(self.client, "_request", return_value=payload) as m:
            result = self.client.list_room_events(RoomEventsQuery(room_id="r-1"))
        self.assertEqual(len(result.events), 2)
        self.assertEqual(result.events[0].id, "e1")
        self.assertEqual(result.next_cursor, "c-2")
        m.assert_called_once()

    def test_list_room_events_handles_missing_keys(self):
        with patch.object(self.client, "_request", return_value={"events": []}):
            result = self.client.list_room_events(RoomEventsQuery(room_id="r-1"))
        self.assertEqual(result.events, [])
        self.assertIsNone(result.next_cursor)

    def test_list_rooms_returns_list(self):
        payload = {
            "rooms": [
                {"id": "r-1", "name": "general", "active_agents": 3},
                {"id": "r-2", "name": "random", "active_agents": 1},
            ]
        }
        with patch.object(self.client, "_request", return_value=payload):
            rooms = self.client.list_rooms()
        self.assertEqual(len(rooms), 2)
        self.assertEqual(rooms[0].id, "r-1")
        self.assertEqual(rooms[0].name, "general")
        self.assertEqual(rooms[1].active_agents, 1)

    def test_get_room_returns_single(self):
        payload = {"id": "r-7", "name": "core", "active_agents": 5}
        with patch.object(self.client, "_request", return_value=payload):
            room = self.client.get_room("r-7")
        self.assertEqual(room.id, "r-7")
        self.assertEqual(room.name, "core")

    def test_request_wraps_http_errors(self):
        err = HTTPError(
            url="https://api.example.test/r/events",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )
        with patch.object(self.client._opener, "open", side_effect=err):
            with self.assertRaises(EventQueryError) as ctx:
                self.client._request("/r/events", {})
        self.assertIn("429", str(ctx.exception))

    def test_request_wraps_json_decode_errors(self):
        bad_resp = MagicMock()
        bad_resp.read.return_value = b"not json"
        bad_resp.__enter__ = MagicMock(return_value=bad_resp)
        bad_resp.__exit__ = MagicMock(return_value=False)
        with patch.object(self.client._opener, "open", return_value=bad_resp):
            with self.assertRaises(EventQueryError):
                self.client._request("/r/events", {})

    def test_request_retries_on_500(self):
        """A single 500 should be retried; a second 500 should raise."""
        err = HTTPError(
            url="https://api.example.test/r/events",
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=None,
        )
        ok = _fake_response({"events": []})
        with patch.object(
            self.client._opener, "open", side_effect=[err, ok]
        ) as m:
            result = self.client._request("/r/events", {})
        self.assertEqual(result, {"events": []})
        self.assertEqual(m.call_count, 2)


if __name__ == "__main__":
    unittest.main()

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
