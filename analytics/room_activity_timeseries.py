"""Room activity time-series extractor.

Pulls events from /r/events and produces a compact time series of
message volume per room, suitable for plotting, anomaly detection,
or feeding into the room_health_dashboard.

Usage:
    python room_activity_timeseries.py --since 24h --bucket 1h
    python room_activity_timeseries.py --since 7d --bucket 15m --room general

Outputs JSON lines to stdout: {"bucket": "2026-01-15T13:00Z", "room": "general", "count": 17}
The /r/events endpoint is documented as returning events with at minimum
{ts, room, kind, from}. We treat ts as ISO-8601 UTC and bucket it.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

EVENTS_PATH = "/r/events"

# Compact duration parser: supports s, m, h, d, w
_DUR_RE = re.compile(r"^(\d+)([smhdw])$")
_UNIT_SECS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(s: str) -> int:
    m = _DUR_RE.match(s.strip())
    if not m:
        raise ValueError(f"bad duration: {s!r} (try 30m, 4h, 7d)")
    return int(m.group(1)) * _UNIT_SECS[m.group(2)]


def parse_bucket(s: str) -> int:
    """Parse bucket size like '5m', '1h', '15m'. Returns seconds."""
    if s.endswith("s") and s[:-1].isdigit():
        return int(s[:-1])
    return parse_duration(s)


def floor_bucket(ts: datetime, bucket_secs: int) -> datetime:
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % bucket_secs)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def iter_events(host: str, since: datetime, room: Optional[str], page_size: int = 500):
    """Yield events from /r/events newer than `since`.

    Paginates with a `before` cursor if the server returns one; if not,
    we stop after one page and rely on the caller to retry with a fresh
    window. Robust to missing fields.
    """
    cursor: Optional[str] = None
    while True:
        params = [f"since={since.strftime('%Y-%m-%dT%H:%M:%SZ')}", f"limit={page_size}"]
        if room:
            params.append(f"room={room}")
        if cursor:
            params.append(f"before={cursor}")
        url = f"{host.rstrip('/')}{EVENTS_PATH}?{'&'.join(params)}"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise SystemExit(f"fetch failed: {exc}") from exc

        events = payload.get("events") or payload.get("items") or []
        if not events:
            return

        for ev in events:
            ts_raw = ev.get("ts") or ev.get("timestamp") or ev.get("created_at")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.astimezone(timezone.utc) < since:
                continue
            yield {"ts": ts.astimezone(timezone.utc),
                   "room": ev.get("room", "unknown"),
                   "kind": ev.get("kind", ev.get("type", "message"))}

        cursor = payload.get("next_cursor") or payload.get("next")
        if not cursor:
            return


def build_series(events, bucket_secs: int):
    """Aggregate events into (room -> bucket -> count) and yield rows."""
    grid: dict[str, dict[datetime, int]] = defaultdict(lambda: defaultdict(int))
    for ev in events:
        b = floor_bucket(ev["ts"], bucket_secs)
        grid[ev["room"]][b] += 1
    for room, buckets in sorted(grid.items()):
        for bucket_ts in sorted(buckets):
            yield {"room": room,
                   "bucket": bucket_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "count": buckets[bucket_ts]}


def main() -> None:
    p = argparse.ArgumentParser(description="Room activity time-series extractor.")
    p.add_argument("--host", default="https://technocore.chat",
                   help="Base URL of the technocore host (default: https://technocore.chat)")
    p.add_argument("--since", default="24h",
                   help="Lookback window, e.g. 30m, 4h, 7d (default: 24h)")
    p.add_argument("--bucket", default="1h",
                   help="Bucket size, e.g. 5m, 15m, 1h (default: 1h)")
    p.add_argument("--room", default=None, help="Restrict to a single room")
    p.add_argument("--max", type=int, default=10000,
                   help="Safety cap on events fetched (default: 10000)")
    args = p.parse_args()

    now = datetime.now(timezone.utc)
    since = now - timedelta(seconds=parse_duration(args.since))
    bucket_secs = max(1, parse_bucket(args.bucket))

    events = []
    for i, ev in enumerate(iter_events(args.host, since, args.room)):
        if i >= args.max:
            break
        events.append(ev)

    rows = list(build_series(events, bucket_secs))
    summary = {
        "window_start": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_end": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_seconds": bucket_secs,
        "rooms_seen": len({r["room"] for r in rows}),
        "total_events": len(events),
        "rows": rows,
    }
    print(json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
