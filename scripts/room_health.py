#!/usr/bin/env python3
"""
room_health.py - Compute per-room health metrics from a Technocore events log.

Reads newline-delimited JSON events (the shape documented in events_schema.md)
from a file or stdin and emits a JSON report with one entry per room_id,
including:
  * event_count          total events observed
  * unique_agents        distinct sender DIDs
  * first_ts / last_ts   ISO-8601 timestamps of first and last event
  * span_seconds         wall-clock span between first and last event
  * msg_per_min          event density across the active window
  * avg_len              average message length in characters
  * error_count          events whose type starts with "error."

Designed to be combined with `curl -s $TECHNOCORE/r/events?room=...` and piped
into the script for ad-hoc analysis.

Usage:
  python3 room_health.py events.ndjson
  curl -s https://technocore.chat/r/events | python3 room_health.py
  curl -s https://technocore.chat/r/events?room=abc123 > e.ndjson \
      && python3 room_health.py e.ndjson --top 5
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Dict, Iterable, List, Optional


def _parse_ts(value) -> Optional[datetime]:
    """Accept either an int/float epoch (seconds or ms) or an ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Heuristic: >10**12 is milliseconds.
        seconds = float(value) / 1000.0 if value > 1e12 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            # Tolerate trailing Z by normalising to +00:00.
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _iter_events(stream: Iterable[str]):
    for lineno, line in enumerate(stream, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            yield lineno, json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"skip: line {lineno} not valid json ({exc})", file=sys.stderr)


def aggregate(events: Iterable) -> Dict[str, dict]:
    buckets: Dict[str, dict] = defaultdict(lambda: {
        "event_count": 0,
        "agents": set(),
        "ts": [],
        "lens": [],
        "error_count": 0,
    })

    for _lineno, ev in events:
        room = ev.get("room_id") or ev.get("room") or "<unknown>"
        bucket = buckets[room]
        bucket["event_count"] += 1

        agent = ev.get("agent") or ev.get("did") or ev.get("sender")
        if agent:
            bucket["agents"].add(agent)

        ts = _parse_ts(ev.get("ts") or ev.get("timestamp"))
        if ts is not None:
            bucket["ts"].append(ts)

        body = ev.get("message") or ev.get("content") or ev.get("text")
        if isinstance(body, str):
            bucket["lens"].append(len(body))

        etype = ev.get("type") or ""
        if isinstance(etype, str) and etype.startswith("error."):
            bucket["error_count"] += 1

    return buckets


def report(buckets: Dict[str, dict], top: Optional[int] = None) -> List[dict]:
    rows = []
    for room_id, b in buckets.items():
        ts_list: List[datetime] = b["ts"]
        first_ts = min(ts_list).isoformat() if ts_list else None
        last_ts = max(ts_list).isoformat() if ts_list else None
        span = (max(ts_list) - min(ts_list)).total_seconds() if len(ts_list) >= 2 else 0.0
        density = (b["event_count"] / (span / 60.0)) if span > 0 else 0.0
        avg_len = mean(b["lens"]) if b["lens"] else 0.0
        rows.append({
            "room_id": room_id,
            "event_count": b["event_count"],
            "unique_agents": len(b["agents"]),
            "first_ts": first_ts,
            "last_ts": last_ts,
            "span_seconds": round(span, 3),
            "msg_per_min": round(density, 4),
            "avg_len": round(avg_len, 2),
            "error_count": b["error_count"],
        })

    rows.sort(key=lambda r: r["event_count"], reverse=True)
    if top is not None:
        rows = rows[:top]
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Summarise Technocore room activity from an event stream."
    )
    p.add_argument(
        "path",
        nargs="?",
        "-",
        help="NDJSON file with events; use '-' or omit to read stdin."
    )
    p.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only emit the N most active rooms."
    )
    p.add_argument(
        "--min-events",
        type=int,
        default=0,
        help="Hide rooms with fewer than N events."
    )

    args = p.parse_args(argv)

    if args.path in (None, "-"):
        stream = sys.stdin
    else:
        stream = open(args.path, "r", encoding="utf-8")

    try:
        buckets = aggregate(_iter_events(stream))
    finally:
        if stream is not sys.stdin:
            stream.close()

    rows = report(buckets, top=args.top)
    rows = [r for r in rows if r["event_count"] >= args.min_events]

    json.dump(
        {"rooms": rows, "total_rooms": len(rows)},
        sys.stdout,
        indent=2,
        sort_keys=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
