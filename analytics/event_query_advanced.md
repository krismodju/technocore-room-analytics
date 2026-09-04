# Advanced /r/events Query Techniques

This guide covers advanced filtering, paging, and aggregation patterns against the
technocore `/r/events` endpoint. It complements `event_query.md` and the examples
in `event_query_examples.md`.

## 1. Endpoint recap

```
GET /r/events?room={room}&type={type}&actor={actor}&since={ts}&until={ts}&limit={n}&cursor={c}
```

All parameters are optional. `room` is the room ID (or `*` for the whole server).
`type` accepts a single event kind or a comma-separated list. `since` and `until`
are epoch milliseconds. Results are returned newest-first; `cursor` is opaque.

## 2. Multi-type filtering with set semantics

`type` is interpreted as a logical OR. To query several kinds in one request:

```
GET /r/events?room=*&type=join,leave,message&since=1715000000000&limit=500
```

If you need AND semantics (e.g., only `message` events from a specific actor),
add `actor` and post-filter client-side, since there is no `not_type` flag:

```python
from analytics.event_query_client import fetch_events
msgs = [e for e in fetch_events(room='*', type='message', actor='did:key:z6Mk...')
        if e['type'] != 'system']
```

## 3. Time-windowed bursts

To find chatty rooms in a sliding window, pair `since`/`until` with a tight
`limit` and walk pages via `cursor`. Pseudocode:

```python
def burstiest_rooms(client, since_ms, until_ms, page=500):
    counts = {}
    cursor = None
    while True:
        page_evs = client.fetch(room='*', since=since_ms, until=until_ms,
                                limit=page, cursor=cursor, type='message')
        if not page_evs:
            break
        for e in page_evs:
            counts[e['room']] = counts.get(e['room'], 0) + 1
        cursor = page_evs[-1].get('next_cursor')
        if not cursor:
            break
    return sorted(counts.items(), key=lambda kv: -kv[1])
```

## 4. Cursors and pagination gotchas

- `cursor` is *exclusive*: the event it points to is **not** repeated on the
  next page. Treat it as a resume token, not a starting key.
- Hard-cap `limit` at 1000. Servers reject larger values with `400 limit_too_large`.
- If `until` falls inside a page boundary, the server still returns the whole
  page; trim client-side.
- Empty result sets return `{"events": [], "next_cursor": null}`, **not** 404.

## 5. Aggregation patterns

### 5.1 Per-actor activity histogram

Bucket events into 1-minute bins per actor:

```python
import collections, time
def actor_histogram(events, bin_sec=60):
    hist = collections.defaultdict(lambda: collections.Counter())
    for e in events:
        b = int(e['ts'] // (bin_sec * 1000))
        hist[e['actor']][b] += 1
    return hist
```

### 5.2 Type-mix ratio

Useful for spotting rooms that flipped from chat to near-silent:

```python
def type_mix(events):
    c = collections.Counter(e['type'] for e in events)
    total = sum(c.values()) or 1
    return {k: v / total for k, v in c.items()}
```

### 5.3 Distinct active actors

`actor` events are not the only kind that proves presence: a `message` or
`react` is also evidence. Union them:

```python
ACTIVE_TYPES = {'join', 'message', 'react', 'poll_vote'}
def distinct_active(events):
    return {e['actor'] for e in events if e['type'] in ACTIVE_TYPES}
```

## 6. Combining with /rooms discovery

`room_discovery.py` already produces candidate room IDs by activity tier. Hand
the top-N IDs to the event client to drill into *why* a room is hot:

```python
from analytics.room_discovery import top_rooms
from analytics.event_query_client import EventQueryClient

hot = top_rooms(n=10)  # list[{'room': id, 'score': float}]
cli = EventQueryClient()
for r in hot:
    evs = cli.fetch(room=r['room'], since=now_ms() - 3600_000, type='message')
    r['recent_msgs'] = len(evs)
    r['distinct_chatters'] = len({e['actor'] for e in evs})
```

## 7. Rate-limit etiquette

- Default budget: ~30 req/min per DID. Spread bursts.
- Use `limit=1000` over many small pages; fewer round-trips cost less.
- Cache the first page of `/rooms` for at least 60s; it changes slowly.
- On `429 slow_down`, honor the `retry_after_ms` field exactly.

## 8. Common pitfalls

| Symptom                                  | Likely cause                                  |
|------------------------------------------|-----------------------------------------------|
| `events` empty even though room is busy  | `since` is in the future (epoch ms confusion) |
| Duplicate rows across pages              | Ignoring `next_cursor`; refetching same page  |
| `actor` filter returns others' events    | Server treats `actor` as prefix, not exact    |
| Counts off by one                         | Off-by-one between `since` (inclusive) and page boundaries |

## 9. A reusable recipe: "health snapshot"

Pull a 1-hour snapshot of one room with three queries:

```python
def snapshot(client, room_id, now_ms):
    base = dict(room=room_id, since=now_ms - 3_600_000, until=now_ms, limit=1000)
    msgs = client.fetch(**base, type='message')
    joins = client.fetch(**base, type='join')
    leaves = client.fetch(**base, type='leave')
    return {
        'window_min': 60,
        'messages': len(msgs),
        'joins': len(joins),
        'leaves': len(leaves),
        'net_growth': len(joins) - len(leaves),
        'top_chatter': collections.Counter(e['actor'] for e in msgs).most_common(1),
    }
```

This is the building block used by `room_health_dashboard.py`; keeping it here
makes the contract between discovery and analytics explicit and copy-pasteable.

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
