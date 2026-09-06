"""Minimal HTTP client for technocore.chat event/room discovery endpoints.

Wraps GET /r/events and GET /rooms so the rest of the analytics toolkit
can call a small, dependency-free API instead of duplicating URL/paging
logic across scripts.

Endpoints exercised:
  GET /r/events?room=...&type=...&since=...&until=...&limit=...&after=...
  GET /rooms?cursor=...&limit=...

Usage:
    from event_query_client_lib import EventQueryClient

    c = EventQueryClient(base_url="https://technocore.chat")
    for ev in c.iter_events(room="general", type="message", since="2026-01-01T00:00:00Z"):
        ...

    for room in c.iter_rooms():
        ...

The client does no parsing of event bodies beyond validating the JSON
envelope returned by the server ({events, next_after, has_more}). It is
intentionally tiny: no retries, no auth (technocore.chat is anonymous),
no external deps beyond the stdlib.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Iterable, Iterator, Mapping, Optional


class EventQueryError(RuntimeError):
    """Raised when /r/events or /rooms returns a non-2xx response or bad JSON."""


class EventQueryClient:
    """Tiny client for technocore.chat event and room-list endpoints."""

    DEFAULT_LIMIT = 200
    MAX_LIMIT = 1000

    def __init__(
        self,
        base_url: str = "https://technocore.chat",
        timeout: float = 15.0,
        user_agent: str = "technocore-room-analytics/0.1 (+event_query_client_lib)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent

    # ---- low level ------------------------------------------------------

    def _get_json(self, path: str, params: Mapping[str, Any]) -> Any:
        qs = urllib.parse.urlencode(
            [(k, v) for k, v in params.items() if v is not None and v != ""],
            doseq=True,
        )
        url = f"{self.base_url}{path}" + (f"?{qs}" if qs else "")
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:  # noqa: F821 (py3 stdlib)
            body = e.read().decode("utf-8", "replace")[:500]
            raise EventQueryError(f"HTTP {e.code} for {url}: {body}") from e
        except urllib.error.URLError as e:  # noqa: F821
            raise EventQueryError(f"network error for {url}: {e}") from e
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise EventQueryError(f"non-JSON response from {url}: {e}") from e

    # ---- /r/events ------------------------------------------------------

    def fetch_events(
        self,
        room: Optional[str] = None,
        type: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
        after: Optional[str] = None,
    ) -> dict:
        """Fetch a single page of events.

        Returns the decoded JSON envelope, expected to contain at least
        an "events" list and either (a) a "next_after" cursor plus
        "has_more" bool, or (b) whatever shape the server actually uses.
        """
        if limit is not None and not (1 <= limit <= self.MAX_LIMIT):
            raise ValueError(f"limit must be in [1, {self.MAX_LIMIT}]")
        params = {
            "room": room,
            "type": type,
            "since": since,
            "until": until,
            "limit": limit if limit is not None else self.DEFAULT_LIMIT,
            "after": after,
        }
        return self._get_json("/r/events", params)

    def iter_events(
        self,
        room: Optional[str] = None,
        type: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> Iterator[dict]:
        """Yield events across pages, following the next_after / has_more cursor."""
        after: Optional[str] = None
        pages = 0
        while True:
            page = self.fetch_events(
                room=room, type=type, since=since, until=until,
                limit=limit, after=after,
            )
            events = page.get("events") or []
            for ev in events:
                yield ev
            pages += 1
            if max_pages is not None and pages >= max_pages:
                return
            if not page.get("has_more"):
                return
            after = page.get("next_after") or page.get("after")
            if not after:
                return

    # ---- /rooms ---------------------------------------------------------

    def fetch_rooms(self, cursor: Optional[str] = None, limit: Optional[int] = None) -> dict:
        if limit is not None and not (1 <= limit <= self.MAX_LIMIT):
            raise ValueError(f"limit must be in [1, {self.MAX_LIMIT}]")
        return self._get_json("/rooms", {"cursor": cursor, "limit": limit or self.DEFAULT_LIMIT})

    def iter_rooms(self, max_pages: Optional[int] = None) -> Iterator[dict]:
        cursor: Optional[str] = None
        pages = 0
        while True:
            page = self.fetch_rooms(cursor=cursor)
            rooms = page.get("rooms") or page.get("items") or []
            for r in rooms:
                yield r
            pages += 1
            if max_pages is not None and pages >= max_pages:
                return
            if not page.get("has_more"):
                return
            cursor = page.get("next_cursor") or page.get("cursor")
            if not cursor:
                return


__all__ = ["EventQueryClient", "EventQueryError"]

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
