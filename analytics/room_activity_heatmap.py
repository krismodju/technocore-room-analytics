"""Room activity heatmap generator.

Aggregates event volume across rooms and hours-of-day to surface when each
room is most active. Pulls from /r/events (paginated) and emits a JSON
matrix suitable for client-side rendering or terminal display.

Usage:
    python room_activity_heatmap.py [--hours 168] [--rooms 20] [--base https://technocore.chat]

Deps: stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_BASE = "https://technocore.chat"
DEFAULT_HOURS = 168  # last 7 days
DEFAULT_ROOM_LIMIT = 20


def fetch_events(base: str, room_id: str, since_ts: int, limit: int = 200) -> list[dict]:
    """Page through /r/events for a room, returning events newer than since_ts."""
    out: list[dict] = []
    cursor = None
    while True:
        q = {"room": room_id, "limit": limit}
        if cursor:
            q["cursor"] = cursor
        url = f"{base}/r/events?{urllib.parse.urlencode(q)}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"[warn] fetch failed for {room_id}: {exc}", file=sys.stderr)
            break
        batch = payload.get("events") or payload.get("items") or []
        if not batch:
            break
        for ev in batch:
            ts = ev.get("ts") or ev.get("created_at") or 0
            if ts >= since_ts:
                out.append(ev)
        cursor = payload.get("next_cursor") or payload.get("next")
        if not cursor:
            break
    return out


def discover_rooms(base: str, limit: int) -> list[str]:
    url = f"{base}/rooms?limit={limit}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rooms = data.get("rooms") or data.get("items") or []
    ids = []
    for r in rooms:
        rid = r.get("id") or r.get("name")
        if rid:
            ids.append(rid)
    return ids[:limit]


def bucket_hour(ts: int) -> int:
    return datetime.fromtimestamp(ts, tz=timezone.utc).hour


def build_matrix(events_by_room: dict[str, list[dict]]) -> dict:
    """Return {room: [24 ints]} plus totals and peak-hour metadata."""
    hours = list(range(24))
    matrix = {}
    for room, evs in events_by_room.items():
        row = [0] * 24
        for ev in evs:
            ts = ev.get("ts") or ev.get("created_at") or 0
            if ts:
                row[bucket_hour(ts)] += 1
        peak = max(range(24), key=lambda h: row[h])
        matrix[room] = {
            "hourly": row,
            "total": sum(row),
            "peak_hour_utc": peak,
            "quietest_hour_utc": min(range(24), key=lambda h: row[h]),
        }
    return matrix


def render_ascii(matrix: dict) -> str:
    rooms = sorted(matrix.keys(), key=lambda r: matrix[r]["total"], reverse=True)
    if not rooms:
        return "(no activity)"
    lines = []
    header = "room".ljust(24) + " " + "".join(str(h % 10) for h in range(24)) + "  total"
    lines.append(header)
    lines.append("-" * len(header))
    for r in rooms:
        row = matrix[r]
        bars = []
        max_v = max(row["hourly"]) or 1
        for v in row["hourly"]:
            if v == 0:
                bars.append(" ")
            elif v >= max_v * 0.75:
                bars.append("#")
            elif v >= max_v * 0.4:
                bars.append("+")
            else:
                bars.append(".")
        lines.append(r[:24].ljust(24) + " " + "".join(bars) + f"  {row['total']:>5}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Build a UTC hour-of-day activity heatmap per room.")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    p.add_argument("--rooms", type=int, default=DEFAULT_ROOM_LIMIT)
    p.add_argument("--json", action="store_true", help="emit JSON instead of ASCII")
    args = p.parse_args(argv)

    since_ts = int(time.time()) - args.hours * 3600
    rooms = discover_rooms(args.base, args.rooms)
    if not rooms:
        print("[err] no rooms discovered", file=sys.stderr)
        return 1

    events_by_room: dict[str, list[dict]] = {}
    for rid in rooms:
        evs = fetch_events(args.base, rid, since_ts)
        if evs:
            events_by_room[rid] = evs

    matrix = build_matrix(events_by_room)
    if args.json:
        json.dump({
            "window_hours": args.hours,
            "since_ts": since_ts,
            "generated_at": int(time.time()),
            "rooms": matrix,
        }, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"# Heatmap over last {args.hours}h (UTC hour-of-day buckets)\n")
        print(render_ascii(matrix))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
