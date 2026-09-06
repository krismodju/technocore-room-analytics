#!/usr/bin/env python3
"""active_users_by_room.py

Compute per-room active-user counts from /r/events.

An "active user" within a window is any distinct user_did that authored at
least one event in that room during the window. This is a useful engagement
metric on top of the raw event volume that trending_rooms_detector.py and
room_activity_heatmap.py already summarize.

Endpoint:
    GET /r/events?room=<id>&since=<iso>&until=<iso>&limit=<n>

Auth:
    Bearer token in $TC_TOKEN (optional on public reads).

Usage:
    python3 active_users_by_room.py ROOM [--since ISO] [--until ISO] [--limit N]

Examples:
    # last 24h, default limit
    python3 active_users_by_room.py did:key:z6Mk...room

    # explicit window
    python3 active_users_by_room.py did:key:z6Mk...room \
        --since 2026-01-01T00:00:00Z --until 2026-01-02T00:00:00Z --limit 500

Output (stdout, machine-readable lines):
    {"room": "...", "since": "...", "until": "...",
     "events": 137, "users": 23, "top": [{"did": "...", "n": 9}, ...]}

No third-party deps; stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ.get("TC_BASE", "https://technocore.chat")


def _http_json(path: str, params: dict) -> dict:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    tok = os.environ.get("TC_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code} for {url}\n")
        raise


def fetch_events(room: str, since: str | None, until: str | None, limit: int) -> list[dict]:
    params = {"room": room, "limit": str(limit)}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    out: list[dict] = []
    cursor = None
    # best-effort paging if server returns a next cursor
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        resp = _http_json("/r/events", p)
        evs = resp.get("events") or resp.get("items") or []
        out.extend(evs)
        if not evs:
            break
        cursor = resp.get("next_cursor") or resp.get("next")
        if not cursor or len(out) >= limit:
            break
    return out[:limit]


def active_users(events: list[dict]) -> tuple[set[str], Counter]:
    dids: set[str] = set()
    counts: Counter = Counter()
    for ev in events:
        did = ev.get("user_did") or ev.get("author") or ev.get("did")
        if not did:
            continue
        dids.add(did)
        counts[did] += 1
    return dids, counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Count active users in a room over a window.")
    ap.add_argument("room", help="room id (e.g. did:key:z6Mk...room)")
    ap.add_argument("--since", help="ISO-8601 lower bound (inclusive)")
    ap.add_argument("--until", help="ISO-8601 upper bound (exclusive)")
    ap.add_argument("--limit", type=int, default=1000, help="max events to scan (default 1000)")
    args = ap.parse_args()

    events = fetch_events(args.room, args.since, args.until, args.limit)
    dids, counts = active_users(events)

    top = [{"did": d, "n": n} for d, n in counts.most_common(10)]
    result = {
        "room": args.room,
        "since": args.since,
        "until": args.until,
        "events": len(events),
        "users": len(dids),
        "top": top,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
