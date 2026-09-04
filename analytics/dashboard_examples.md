# Dashboard Examples: Visualizing Room Activity

This document shows practical, self-contained examples for building lightweight
dashboards on top of the technocore events API. All examples assume you have
already authenticated and can call `/r/events` (see `event_query_client.py`).

## 1. Activity Heatmap (per-room, per-hour)

Produces a 7 x 24 matrix counting events per room and hour-of-day. Useful for
spotting quiet hours and peak engagement windows.

```python
from datetime import datetime, timezone
from collections import defaultdict
from event_query_client import query_events

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def heatmap(room_id: str, since_ts: int, until_ts: int) -> list[list[int]]:
    grid = [[0] * 24 for _ in range(7)]
    for ev in query_events(room_id=room_id, since=since_ts, until=until_ts):
        t = datetime.fromtimestamp(ev["ts"], tz=timezone.utc)
        grid[t.weekday()][t.hour] += 1
    return grid

def render_ascii(grid) -> str:
    lines = ["    " + " ".join(f"{h:02d}" for h in range(24))]
    for i, row in enumerate(grid):
        lines.append(f"{DAYS[i]} " + " ".join(f"{c:02d}" for c in row))
    return "\n".join(lines)
```

## 2. Top Contributors in a Window

Counts distinct author DIDs that produced events. Helps identify the most
active participants without exposing any message content.

```python
def top_contributors(room_id: str, since_ts: int, until_ts: int, k: int = 10):
    counts: dict[str, int] = defaultdict(int)
    for ev in query_events(room_id=room_id, since=since_ts, until=until_ts):
        if "author" in ev:
            counts[ev["author"]] += 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:k]
```

## 3. Event-Type Distribution

Aggregates counts grouped by `event_type` (e.g. `message`, `join`, `leave`,
`edit`, `react`). Use this to chart a simple pie or stacked bar.

```python
def type_distribution(room_id: str, since_ts: int, until_ts: int) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for ev in query_events(room_id=room_id, since=since_ts, until=until_ts):
        out[ev.get("type", "unknown")] += 1
    return dict(out)
```

## 4. Inter-Event Gaps (Burstiness)

Measures the median and p95 gap (seconds) between consecutive events in a
room. A low p95 with a high median means a steady stream; a high p95 means
periodic bursts.

```python
import statistics

def burst_stats(room_id: str, since_ts: int, until_ts: int):
    timestamps = [ev["ts"] for ev in query_events(
        room_id=room_id, since=since_ts, until=until_ts)]
    timestamps.sort()
    gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
    if not gaps:
        return {"events": len(timestamps), "median_gap": None, "p95_gap": None}
    gaps.sort()
    p95 = gaps[int(len(gaps) * 0.95) - 1]
    return {
        "events": len(timestamps),
        "median_gap": statistics.median(gaps),
        "p95_gap": p95,
    }
```

## 5. Room Discovery Score

Combines recency and activity into a single sortable score so `/rooms`
listings can be ranked. Higher means fresher and more active.

```python
def discovery_score(recency_hours: float, events_last_24h: int) -> float:
    # Decay over 48h; saturate at ~100 events.
    import math
    recency = math.exp(-recency_hours / 48.0)
    activity = min(events_last_24h, 100) / 100.0
    return round(0.6 * recency + 0.4 * activity, 4)
```

## Putting it together

A minimal daily report for a room list:

```python
def daily_report(rooms, since_ts, until_ts):
    for rid in rooms:
        print(rid,
              "events=", sum(type_distribution(rid, since_ts, until_ts).values()),
              "types=", type_distribution(rid, since_ts, until_ts),
              "burst=", burst_stats(rid, since_ts, until_ts))
```

All snippets are dependency-light (stdlib only besides the client module)
and safe to copy into a notebook or a small Flask/Streamlit dashboard.

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
