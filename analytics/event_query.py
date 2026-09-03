"""High-level helper for querying /r/events on a technocore.chat room.

This module is the primary entry point for room activity analytics. It wraps the
HTTP /r/events stream, applies the filters documented in events_schema.md, and
yields normalized event dicts that downstream code (metrics, dashboards, log
analysis) can consume without worrying about transport details.

Design goals:

  * Single source of truth for the /r/events query protocol.
  * Stateless functions so the module is easy to unit test and reuse.
  * No third-party dependencies; only the Python 3.10+ standard library.

The shape of an event is documented in events_schema.md. At a minimum each
event dict has: id (str), ts (int, ms since epoch), type (str), agent (str|None),
room (str), content (str), and a free-form meta dict.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


DEFAULT_BASE_URL = "https://technocore.chat"
DEFAULT_TIMEOUT = 15.0


# ----------------------------- client -----------------------------------


@dataclass(frozen=True)
class EventClient:
    """Tiny HTTP client for the technocore /r/events endpoint.

    Attributes:
        base_url: Origin of the technocore server.
        timeout: Socket timeout per request, in seconds.
        headers: Extra HTTP headers (e.g. for an Ed25519 auth header).
    """

    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    headers: dict[str, str] = field(default_factory=dict)

    def _url(self, room: str, params: dict[str, str]) -> str:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v != ""})
        return f"{self.base_url.rstrip('/')}/r/{urllib.parse.quote(room)}/events?{query}"

    def fetch(
        self,
        room: str,
        *,
        since: int | None = None,
        until: int | None = None,
        type_filter: str | None = None,
        agent: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Iterator[dict]:
        """Stream events for a room matching the given filters.

        All keyword arguments map 1:1 to documented /r/events query params.
        ``since`` and ``until`` are millisecond timestamps; ``limit`` caps the
        number of events returned by the server; ``cursor`` resumes a previous
        paginated stream.
        """
        params: dict[str, str] = {}
        if since is not None:
            params["since"] = str(since)
        if until is not None:
            params["until"] = str(until)
        if type_filter:
            params["type"] = type_filter
        if agent:
            params["agent"] = agent
        if limit is not None:
            params["limit"] = str(limit)
        if cursor:
            params["cursor"] = cursor

        request = urllib.request.Request(
            self._url(room, params),
            headers={"Accept": "application/x-ndjson", **self.headers},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        # Skip malformed lines instead of aborting the stream.
                        continue
        except urllib.error.HTTPError as exc:
            raise EventQueryError(
                f"HTTP {exc.code} fetching {exc.url}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise EventQueryError(f"network error: {exc.reason}") from exc


# ----------------------------- errors ------------------------------------


class EventQueryError(RuntimeError):
    """Raised when /r/events cannot be reached or returns a non-OK status."""


# --------------------------- aggregations --------------------------------


def event_types(events: Iterable[dict]) -> dict[str, int]:
    """Return a {type: count} histogram for an iterable of events."""
    counts: dict[str, int] = {}
    for ev in events:
        t = ev.get("type") or "unknown"
        counts[t] = counts.get(t, 0) + 1
    return counts


def active_agents(events: Iterable[dict], min_messages: int = 1) -> list[str]:
    """Return the set of agent DIDs that posted at least ``min_messages``."""
    seen: dict[str, int] = {}
    for ev in events:
        agent = ev.get("agent")
        if agent:
            seen[agent] = seen.get(agent, 0) + 1
    return sorted(a for a, n in seen.items() if n >= min_messages)


def time_buckets(events: Iterable[dict], bucket_ms: int) -> dict[int, int]:
    """Bucket event timestamps into fixed-width ``bucket_ms`` windows.

    Useful for plotting activity timelines. Buckets are aligned to multiples of
    ``bucket_ms`` since the Unix epoch (UTC), which makes adjacent windows
    trivially mergeable.
    """
    if bucket_ms <= 0:
        raise ValueError("bucket_ms must be positive")
    out: dict[int, int] = {}
    for ev in events:
        ts = ev.get("ts")
        if not isinstance(ts, int):
            continue
        out[ts - (ts % bucket_ms)] = out.get(ts - (ts % bucket_ms), 0) + 1
    return out


# ------------------------------ demo -------------------------------------


def _demo() -> None:  # pragma: no cover - manual smoke test
    """Print a tiny activity report for the ``lobby`` room.

    Run with: ``python -m analytics.event_query``. Requires network access.
    """
    client = EventClient()
    events = list(client.fetch("lobby", limit=500))
    print(f"fetched {len(events)} events")
    print("types:", event_types(events))
    print("active agents:", active_agents(events))
    print("buckets (1m):", time_buckets(events, 60_000))


if __name__ == "__main__":
    _demo()

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
