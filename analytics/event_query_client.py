"""
event_query_client.py — A small client library for the technocore.chat /r/events endpoint.

This module wraps the raw HTTP API described in events_schema.md and provides a
typed, iterator-friendly interface for retrieving room events in ascending or
descending order, with optional time-window and room filtering.

It is intentionally dependency-light (only the Python standard library) so it
can be dropped into any analytics pipeline or notebook without extra installs.

Example:

    from analytics.event_query_client import EventQueryClient

    client = EventQueryClient(base_url="https://technocore.chat", token=None)
    for evt in client.iter_room_events("general", limit=50, direction="backward"):
        print(evt["id"], evt["ts"], evt["type"], evt.get("from", ""))
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional


class EventQueryError(RuntimeError):
    """Raised when the /r/events endpoint returns an error or unexpected payload."""


class EventQueryClient:
    """Thin client over the technocore /r/events streaming endpoint.

    Parameters
    ----------
    base_url:
        Origin of the technocore server, e.g. ``"https://technocore.chat"``.
        No trailing slash.
    token:
        Optional bearer token. Most public rooms do not require auth, but
        private rooms may. If supplied it is sent as ``Authorization: Bearer``.
    timeout:
        Per-request timeout in seconds for the underlying urllib call.
    user_agent:
        Custom UA string. Defaults to ``"room-scope/1.0"``.
    """

    DEFAULT_USER_AGENT = "room-scope/1.0"

    def __init__(
        self,
        base_url: str = "https://technocore.chat",
        token: Optional[str] = None,
        timeout: float = 30.0,
        user_agent: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    # ------------------------------------------------------------------ HTTP
    def _request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        qs = ""
        if params:
            # drop None values so the server only sees real filters
            clean = {k: v for k, v in params.items() if v is not None}
            qs = "?" + urllib.parse.urlencode(clean, doseq=True)
        url = f"{self.base_url}{path}{qs}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", self.user_agent)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise EventQueryError(f"HTTP {e.code} from {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise EventQueryError(f"connection error for {url}: {e.reason}") from e
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise EventQueryError(f"invalid JSON from {url}: {e}") from e

    # ----------------------------------------------------- public interface
    def list_rooms(self) -> List[Dict[str, Any]]:
        """Return the list of rooms known to the server.

        Uses ``GET /rooms`` and returns the raw array. Each entry is expected
        to contain at minimum ``id`` and ``title`` keys (see events_schema.md).
        """
        data = self._request("/rooms")
        if not isinstance(data, list):
            raise EventQueryError(f"/rooms did not return a list: {type(data).__name__}")
        return data

    def iter_room_events(
        self,
        room_id: str,
        *,
        limit: int = 100,
        direction: str = "backward",
        since_ts: Optional[int] = None,
        until_ts: Optional[int] = None,
        event_type: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield events for ``room_id`` in the requested order.

        Parameters
        ----------
        room_id:
            The room identifier (the ``id`` field from ``/rooms``).
        limit:
            Maximum number of events to fetch in a single page. The server
            caps this; values above the cap are passed through and may be
            truncated by the server.
        direction:
            ``"backward"`` (default, newest first) or ``"forward"``
            (oldest first, useful for full backfills).
        since_ts, until_ts:
            Optional unix-second timestamps forming an inclusive half-open
            window ``[since_ts, until_ts]``. Pass only one to do an open-ended
            query.
        event_type:
            Optional filter for ``message``, ``join``, ``leave``, etc.

        Yields
        ------
        dict
            Individual event objects as documented in events_schema.md.
        """
        if direction not in ("forward", "backward"):
            raise ValueError("direction must be 'forward' or 'backward'")

        cursor: Optional[str] = None
        yielded = 0
        while True:
            page = self._fetch_event_page(
                room_id=room_id,
                limit=limit,
                direction=direction,
                cursor=cursor,
                since_ts=since_ts,
                until_ts=until_ts,
                event_type=event_type,
            )
            events = page.get("events", [])
            for evt in events:
                yield evt
                yielded += 1
            cursor = page.get("next_cursor")
            if not cursor or not events:
                return

    # ------------------------------------------------------------- internals
    def _fetch_event_page(
        self,
        *,
        room_id: str,
        limit: int,
        direction: str,
        cursor: Optional[str],
        since_ts: Optional[int],
        until_ts: Optional[int],
        event_type: Optional[str],
    ) -> Dict[str, Any]:
        params = {
            "room": room_id,
            "limit": int(limit),
            "dir": direction,
            "cursor": cursor,
            "since": since_ts,
            "until": until_ts,
            "type": event_type,
        }
        data = self._request("/r/events", params=params)
        if not isinstance(data, dict) or "events" not in data:
            raise EventQueryError(
                f"/r/events returned unexpected payload shape: {type(data).__name__}"
            )
        return data


__all__ = ["EventQueryClient", "EventQueryError"]

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
