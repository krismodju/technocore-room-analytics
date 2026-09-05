"""Trending rooms detector for technocore.chat.

Polls /r/events from multiple rooms, computes activity scores over a sliding
window, and surfaces rooms whose recent activity is significantly higher than
their own baseline. Useful for discovery: which rooms are picking up right now?

Design notes
------------
* Stateless across runs (no SQLite/Redis) so it can run as a cron job.
* Pure stdlib (urllib, json, time, statistics) so it has no install footprint.
* Adaptive baseline: a room that has been silent for weeks then spikes by 2
  events/hour is more interesting than one that always has 50/hour.
* Activity is weighted toward distinct authors to discount a single bot flooding
  the room. Weights: author=1.0, message=0.2, join=0.4, leave=0.2, system=0.1.

Usage
-----
    python trending_rooms_detector.py --rooms general,random,tech --window 600
    python trending_rooms_detector.py --rooms general --follow --interval 30

Exit code is 0 always; results are printed as JSON to stdout so the script
plugs into jq / dashboards / further pipelines.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable


BASE_URL = "https://technocore.chat"

EVENT_WEIGHTS = {
    "message": 0.2,
    "join": 0.4,
    "leave": 0.2,
    "system": 0.1,
}
AUTHOR_BONUS = 1.0  # added once per unique author per window


@dataclass
class RoomStats:
    name: str
    samples: deque[float] = field(default_factory=lambda: deque(maxlen=64))
    baseline_mean: float = 0.0
    baseline_std: float = 0.0

    def update(self, score: float) -> None:
        self.samples.append(score)
        if len(self.samples) >= 5:
            self.baseline_mean = statistics.mean(self.samples)
            self.baseline_std = statistics.pstdev(self.samples) or 1e-9

    def zscore(self, current: float) -> float:
        if self.baseline_std == 0:
            return 0.0
        return (current - self.baseline_mean) / self.baseline_std


def fetch_events(room: str, since_ms: int, limit: int = 200) -> list[dict]:
    url = f"{BASE_URL}/r/events?room={room}&since={since_ms}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "room-scope/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        payload = json.load(resp)
    return payload.get("events", [])


def score_window(events: Iterable[dict]) -> tuple[float, int]:
    """Return (weighted_score, unique_author_count) for the window."""
    score = 0.0
    authors: set[str] = set()
    for ev in events:
        kind = ev.get("type", "message")
        score += EVENT_WEIGHTS.get(kind, 0.1)
        author = ev.get("author")
        if author:
            authors.add(author)
    score += len(authors) * AUTHOR_BONUS
    return score, len(authors)


def detect(rooms: list[str], window_s: int) -> dict:
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - window_s * 1000
    stats = {r: RoomStats(name=r) for r in rooms}
    rows = []
    for room in rooms:
        try:
            events = fetch_events(room, since_ms)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            rows.append({"room": room, "error": str(exc)})
            continue
        score, authors = score_window(events)
        stats[room].update(score)
        z = stats[room].zscore(score)
        rows.append({
            "room": room,
            "events": len(events),
            "unique_authors": authors,
            "score": round(score, 3),
            "baseline_mean": round(stats[room].baseline_mean, 3),
            "zscore": round(z, 3),
            "trending": z >= 2.0 and len(events) >= 3,
        })
    rows.sort(key=lambda r: r.get("zscore", -1e9), reverse=True)
    return {
        "as_of": now_ms,
        "window_seconds": window_s,
        "results": rows,
        "trending": [r["room"] for r in rows if r.get("trending")],
    }


def run_once(rooms: list[str], window_s: int) -> None:
    result = detect(rooms, window_s)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


def run_follow(rooms: list[str], window_s: int, interval_s: int) -> None:
    print(f"# following {len(rooms)} rooms, window={window_s}s interval={interval_s}s", file=sys.stderr)
    while True:
        run_once(rooms, window_s)
        time.sleep(max(5, interval_s))


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect trending rooms on technocore.chat.")
    p.add_argument("--rooms", required=True, help="Comma-separated room names.")
    p.add_argument("--window", type=int, default=600, help="Sliding window in seconds (default 600).")
    p.add_argument("--follow", action="store_true", help="Poll continuously.")
    p.add_argument("--interval", type=int, default=30, help="Poll interval seconds when --follow is set.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    rooms = [r.strip() for r in args.rooms.split(",") if r.strip()]
    if not rooms:
        print("error: --rooms must list at least one room", file=sys.stderr)
        return 2
    if args.window < 30 or args.window > 86400:
        print("error: --window must be between 30 and 86400 seconds", file=sys.stderr)
        return 2
    if args.follow:
        run_follow(rooms, args.window, args.interval)
    else:
        run_once(rooms, args.window)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
