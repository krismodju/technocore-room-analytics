# Aggregation Examples for technocore Room Activity

These examples show how to roll up `/r/events` streams into the activity metrics exposed by `analytics/activity_metrics.py`. All examples assume the client returned a list of event objects matching `events_schema.md`.

## 1. Hourly message volume per room

Bucket events whose `type == "message"` into one-hour windows keyed by `(room_id, hour_bucket)`. Useful for spotting bursts and quiet periods.

```python
from collections import Counter
from datetime import datetime

def hour_bucket(ts: str) -> str:
    # ts format: "2026-01-15T13:45:02Z"
    return ts[:13] + ":00"

def hourly_volume(events):
    counts = Counter()
    for ev in events:
        if ev.get("type") != "message":
            continue
        key = (ev["room_id"], hour_bucket(ev["ts"]))
        counts[key] += 1
    return [
        {"room_id": rid, "hour": h, "messages": n}
        for (rid, h), n in sorted(counts.items())
    ]
```

## 2. Unique participant count per room (rolling window)

Count distinct `actor_did` values that emitted any event in a given room over the full event list. Combine with a date filter on `ts` for sliding windows.

```python
def unique_participants(events, room_id=None):
    actors = set()
    for ev in events:
        if room_id and ev["room_id"] != room_id:
            continue
        actors.add(ev["actor_did"])
    return {"room_id": room_id, "unique_actors": len(actors), "actors": sorted(actors)}
```

## 3. Type distribution heatmap data

Produce a `{room_id: {event_type: count}}` matrix suitable for a heatmap.

```python
from collections import defaultdict

def type_heatmap(events):
    matrix = defaultdict(lambda: defaultdict(int))
    for ev in events:
        matrix[ev["room_id"]][ev["type"]] += 1
    return {rid: dict(types) for rid, types in matrix.items()}
```

## 4. First and last activity per room

Min and max `ts` per `room_id`, useful for room liveness checks.

```python
def activity_span(events):
    spans = {}
    for ev in events:
        rid = ev["room_id"]
        ts = ev["ts"]
        if rid not in spans:
            spans[rid] = {"first": ts, "last": ts, "count": 0}
        s = spans[rid]
        if ts < s["first"]:
            s["first"] = ts
        if ts > s["last"]:
            s["last"] = ts
        s["count"] += 1
    return spans
```

## 5. Combining with `event_query_client.py`

```python
from event_query_client import fetch_events
from activity_metrics import summarize_room

# Fetch the last 1000 events from a room
raw = fetch_events(room_id="r-general", limit=1000)
rollup = summarize_room(raw)
heatmap = type_heatmap(raw)
span = activity_span(raw).get("r-general", {})

print(rollup, heatmap, span)
```

## Notes

- All timestamps are UTC ISO-8601 with a trailing `Z`; lexicographic comparison is safe for min/max.
- `actor_did` may be `"anonymous"` for pre-auth events; include or exclude as your metric requires.
- For large streams, prefer `event_query.py` filters server-side before aggregating client-side.

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
