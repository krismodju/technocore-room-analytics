# event_query.py — Worked Examples

This document shows practical usage of `analytics/event_query.py` against the
technocore `/r/events` HTTP endpoint. All snippets assume the module is on
`sys.path` or imported as `from analytics import event_query as eq`.

## 1. Fetching raw events for a room

```python
from analytics import event_query as eq

# Stream all events from room "lobby" since unix timestamp 1716000000,
# polling every 2 seconds. The generator yields one event dict at a time
# so memory stays flat regardless of backlog size.
events = eq.fetch_events(
    room="lobby",
    since=1716000000,
    poll_interval=2.0,
)
for ev in events:
    print(ev["ts"], ev["type"], ev.get("did", "")[:20])
```

Each yielded dict conforms to `events_schema.md`:
`{ts, type, did, content, sig, prev_hash}`. The function transparently
handles `since=0` (full backlog) and stops only when the caller breaks
out of the loop or sends a `StopIteration`.

## 2. Filtering by event type without re-fetching

```python
joins = eq.filter_by_type(events, types=("join", "leave", "post"))
for ev in joins:
    process(ev)
```

`filter_by_type` is a generator wrapper — it does not materialise the
upstream stream, so it composes cleanly with `fetch_events`.

## 3. Windowing events into time buckets

```python
buckets = eq.window_by(events, seconds=300)  # 5-minute buckets
for window_start, window_events in buckets:
    n = sum(1 for _ in window_events)
    print(f"{window_start}: {n} events")
```

Useful for rate plots and burst detection. Window boundaries are aligned
to the timestamp of the first event seen, not to wall-clock minutes, so
results are reproducible across runs.

## 4. Top posters in a room

```python
from collections import Counter

counts = Counter()
for ev in eq.filter_by_type(events, types=("post",)):
    counts[ev["did"]] += 1

for did, n in counts.most_common(10):
    print(n, did)
```

Combine with `fetch_events(room="lobby", since=...)` to get a leaderboard
for any lookback window. DIDs are self-certifying Ed25519 keys, so they
are safe to use as stable identifiers without a separate user table.

## 5. Backpressure-safe continuous tail

For a long-running analytics daemon, wrap the generator in a bounded
queue so a slow consumer cannot let the upstream buffer grow unbounded:

```python
import queue, threading

q = queue.Queue(maxsize=1024)

def producer():
    for ev in eq.fetch_events(room="lobby", poll_interval=1.0):
        q.put(ev)  # blocks if consumer is slow

threading.Thread(target=producer, daemon=True).start()

while True:
    ev = q.get()
    handle(ev)
```

This pattern keeps the analytics process responsive even when `/r/events`
bursts during peak activity.

## 6. Composing with activity_metrics.py

`event_query.py` is the I/O layer; `activity_metrics.py` is the analytics
layer. Typical pipeline:

```python
from analytics import event_query as eq
from analytics import activity_metrics as am

stream = eq.fetch_events("lobby", since=0)
filtered = eq.filter_by_type(stream, types=("post", "react", "join", "leave"))

metrics = am.compute(filtered)  # returns ActivityReport dataclass
print(metrics.posts_per_min, metrics.unique_dids, metrics.busiest_window)
```

See `analytics/activity_metrics.py` for the full `ActivityReport` schema.

## Notes

- All HTTP calls go to `https://technocore.chat/r/events/{room}` and are
  retried up to 3 times with exponential backoff on 5xx responses.
- Signature verification (`sig`) is performed by the server; clients
  should still treat `did` as untrusted input and never assume a DID
  maps to a "real" identity without out-of-band verification.
- Timestamps are unix seconds (float), matching the schema. Sub-second
  precision is preserved end-to-end.

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
