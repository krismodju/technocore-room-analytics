#!/usr/bin/env python3
"""Detect anomalous activity bursts in technocore rooms.

Reads events from the /r/events endpoint (via event_query_client_lib) and
flags rooms whose short-window event rate deviates significantly from their
own rolling baseline. Useful for spotting spam storms, coordination bursts,
coordinated raids, or sudden quiet periods worth investigating.

Algorithm (per room):
  1. Bucket events into fixed-size time windows (default 5 minutes).
  2. Compute a rolling baseline using the median and MAD of the prior N windows
     (default N=24, i.e. 2 hours of history). Median + MAD is robust to the
     very bursts we are trying to detect.
  3. Define an anomaly score: (current - median) / (MAD + 1).
     Score >= burst_z (default 5.0)  -> BURST
     Score <= -quiet_z (default 4.0) -> QUIET

Outputs JSON lines to stdout (one anomaly record per flagged window) and a
human summary to stderr.

CLI examples:
  python3 room_anomaly_detector.py --room general --hours 24
  python3 room_anomaly_detector.py --hours 6 --window-secs 300 --burst-z 4
  python3 room_anomaly_detector.py --room general --hours 12 --json-only

Self-contained: depends only on the project's event_query_client_lib and
the Python 3 stdlib.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import sys
import time
from typing import Iterable

from event_query_client_lib import EventQueryClient  # type: ignore


def _iter_windows(events: Iterable[dict], window_secs: int):
    """Yield (window_start, count) buckets in chronological order."""
    bucket = collections.OrderedDict()
    for ev in events:
        ts = ev.get("ts")
        if ts is None:
            continue
        try:
            t = int(ts)
        except (TypeError, ValueError):
            continue
        w = (t // window_secs) * window_secs
        bucket[w] = bucket.get(w, 0) + 1
    for w in sorted(bucket):
        yield w, bucket[w]


def _rolling_stats(counts: list[int], history: int):
    """Return (median, mad) of the trailing `history` counts, or (0, 0)."""
    if not counts:
        return 0.0, 0.0
    window = counts[-history:] if len(counts) > history else counts[:]
    if not window:
        return 0.0, 0.0
    med = statistics.median(window)
    if len(window) < 2:
        return float(med), 0.0
    mad = statistics.median([abs(x - med) for x in window])
    return float(med), float(mad)


def detect(events: list[dict], window_secs: int, history: int,
           burst_z: float, quiet_z: float):
    """Run the detector. Returns a list of anomaly dicts."""
    history_counts: list[int] = []
    anomalies: list[dict] = []
    for wstart, count in _iter_windows(events, window_secs):
        med, mad = _rolling_stats(history_counts, history)
        score = (count - med) / (mad + 1.0)
        kind = None
        if med >= 2 and score >= burst_z:
            kind = "BURST"
        elif med >= 1 and score <= -quiet_z:
            kind = "QUIET"
        if kind:
            anomalies.append({
                "window_start": wstart,
                "window_end": wstart + window_secs,
                "count": count,
                "baseline_median": round(med, 2),
                "baseline_mad": round(mad, 2),
                "score": round(score, 2),
                "kind": kind,
            })
        history_counts.append(count)
    return anomalies


def _fetch(client: EventQueryClient, room: str | None, hours: int):
    cutoff = int(time.time()) - hours * 3600
    if room:
        return client.query(room=room, since=cutoff, limit=5000)
    # Aggregate across rooms if none specified
    rooms = client.list_rooms() or []
    out: list[dict] = []
    for r in rooms:
        try:
            out.extend(client.query(room=r, since=cutoff, limit=5000))
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"warn: room {r} skipped: {exc}", file=sys.stderr)
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default="https://technocore.chat")
    p.add_argument("--room", default=None, help="room id/name; omit for all")
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--window-secs", type=int, default=300)
    p.add_argument("--history-windows", type=int, default=24,
                   help="rolling baseline length in windows")
    p.add_argument("--burst-z", type=float, default=5.0)
    p.add_argument("--quiet-z", type=float, default=4.0)
    p.add_argument("--json-only", action="store_true")
    args = p.parse_args(argv)

    client = EventQueryClient(base_url=args.base_url)
    events = _fetch(client, args.room, args.hours)
    anomalies = detect(events, args.window_secs, args.history.windows if hasattr(args, "history.windows") else args.history_windows,
                       args.burst_z, args.quiet_z)

    if args.json_only:
        for a in anomalies:
            print(json.dumps(a, separators=(",", ":")))
        return 0

    for a in anomalies:
        print(json.dumps(a, separators=(",", ":")))
    bursts = sum(1 for a in anomalies if a["kind"] == "BURST")
    quiets = sum(1 for a in anomalies if a["kind"] == "QUIET")
    scope = args.room or "ALL_ROOMS"
    print(
        f"\n[{scope}] {args.hours}h window={args.window_secs}s "
        f"events={len(events)} bursts={bursts} quiets={quiets}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
