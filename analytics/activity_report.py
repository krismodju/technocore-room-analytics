"""Generate a human-readable activity report from /r/events.

Reads events from a JSONL file (one event per line, as returned by GET /r/events)
and prints a per-room summary: total events, unique actors, time span,
top event types, and approximate event rate.

Usage:
    python analytics/activity_report.py events.jsonl
    python analytics/activity_report.py events.jsonl --top 5 --rooms general,dev

Event schema (see events_schema.md):
    {"ts": "2026-01-15T12:34:56Z", "room": "general",
     "actor": "did:key:z6Mk...", "type": "message", "size": 42}
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

ISO = "%Y-%m-%dT%H:%M:%SZ"


def load_events(path: Path) -> Iterator[dict]:
    """Yield parsed events from a JSONL file, skipping malformed lines."""
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"warn: skipping line {lineno}: {exc}", file=sys.stderr)


def parse_ts(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp; return None on failure."""
    if not value:
        return None
    try:
        # Accept trailing 'Z' as UTC.
        return datetime.strptime(value.replace("Z", ""), ISO.replace("Z", ""))
    except ValueError:
        return None


def summarize(events: Iterable[dict]) -> dict:
    """Aggregate event counts per room."""
    by_room: dict[str, dict] = defaultdict(lambda: {
        "events": 0,
        "actors": set(),
        "types": Counter(),
        "first_ts": None,
        "last_ts": None,
        "bytes": 0,
    })
    for ev in events:
        room = ev.get("room") or "<unknown>"
        bucket = by_room[room]
        bucket["events"] += 1
        actor = ev.get("actor")
        if actor:
            bucket["actors"].add(actor)
        etype = ev.get("type") or "unknown"
        bucket["types"][etype] += 1
        size = ev.get("size")
        if isinstance(size, (int, float)) and size >= 0:
            bucket["bytes"] += int(size)
        ts = parse_ts(ev.get("ts", ""))
        if ts is not None:
            if bucket["first_ts"] is None or ts < bucket["first_ts"]:
                bucket["first_ts"] = ts
            if bucket["last_ts"] is None or ts > bucket["last_ts"]:
                bucket["last_ts"] = ts
    return by_room


def render(by_room: dict, top_n: int, room_filter: set[str] | None) -> str:
    """Render a human-readable report."""
    lines: list[str] = []
    lines.append("technocore activity report")
    lines.append("=" * 40)
    rooms = sorted(by_room)
    if room_filter:
        rooms = [r for r in rooms if r in room_filter]
    if not rooms:
        return "\n".join(lines + ["(no events matched)"])
    grand_events = 0
    for room in rooms:
        b = by_room[room]
        grand_events += b["events"]
        span = "n/a"
        rate = "n/a"
        if b["first_ts"] and b["last_ts"]:
            secs = max((b["last_ts"] - b["first_ts"]).total_seconds(), 1.0)
            span = f"{(b['last_ts'] - b['first_ts']).total_seconds():.0f}s"
            rate = f"{b['events'] / secs:.3f}/s"
        lines.append("")
        lines.append(f"room: {room}")
        lines.append(f"  events       : {b['events']}")
        lines.append(f"  unique actors: {len(b['actors'])}")
        lines.append(f"  first -> last: {b['first_ts']} -> {b['last_ts']}")
        lines.append(f"  span / rate  : {span}  ({rate})")
        lines.append(f"  bytes        : {b['bytes']}")
        lines.append(f"  top types    :")
        for etype, count in b["types"].most_common(top_n):
            lines.append(f"    - {etype:24s} {count}")
    lines.append("")
    lines.append(f"total events across {len(rooms)} room(s): {grand_events}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", type=Path, help="JSONL events file")
    parser.add_argument("--top", type=int, default=5, help="top N event types per room")
    parser.add_argument("--rooms", type=str, default="",
                        help="comma-separated room whitelist")
    args = parser.parse_args(argv)
    if not args.path.exists():
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    room_filter = {r.strip() for r in args.rooms.split(",") if r.strip()} or None
    by_room = summarize(load_events(args.path))
    print(render(by_room, max(1, args.top), room_filter))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
