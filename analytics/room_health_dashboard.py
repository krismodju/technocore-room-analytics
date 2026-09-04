"""Room health dashboard generator.

Produces a human-readable health report for one or more rooms by combining
activity, participation, and event-type metrics computed via
analytics.event_query_client. The output is plain markdown so it can be
rendered in GitHub, posted to chat, or piped to a static-site generator.

Usage:
    from room_health_dashboard import build_dashboard
    print(build_dashboard("general"))
    print(build_dashboard(["general", "agents"], window="24h"))
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Union

from event_query_client import fetch_events, fetch_rooms


def _parse_window(window: str) -> int:
    """Convert a short duration string like '15m', '6h', '2d' to seconds."""
    if not window:
        return 24 * 3600
    unit = window[-1]
    try:
        value = int(window[:-1])
    except ValueError as exc:
        raise ValueError(f"window must look like '15m', '6h', '2d', got {window!r}") from exc
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    raise ValueError(f"unsupported unit {unit!r}; use s/m/h/d")


def _bucket_events(events: list[dict]) -> dict:
    by_type = Counter()
    by_sender = Counter()
    timestamps: list[float] = []
    for ev in events:
        by_type[ev.get("type", "unknown")] += 1
        sender = ev.get("from") or ev.get("did") or "anonymous"
        by_sender[sender] += 1
        ts = ev.get("ts")
        if ts is not None:
            timestamps.append(float(ts))
    timestamps.sort()
    return {
        "total": len(events),
        "by_type": dict(by_type.most_common()),
        "top_senders": by_sender.most_common(5),
        "first_ts": timestamps[0] if timestamps else None,
        "last_ts": timestamps[-1] if timestamps else None,
    }


def _format_ts(ts: float | None) -> str:
    if ts is None:
        return "n/a"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _score(bucket: dict, window_seconds: int) -> str:
    total = bucket["total"]
    if total == 0:
        return "quiet (no events in window)"
    if window_seconds <= 0:
        return f"active ({total} events)"
    rate = total / (window_seconds / 3600)
    if rate >= 30:
        return f"very busy (~{rate:.1f} events/hour)"
    if rate >= 5:
        return f"active (~{rate:.1f} events/hour)"
    if rate >= 1:
        return f"steady (~{rate:.1f} events/hour)"
    return f"slow (~{rate:.1f} events/hour)"


def build_dashboard(
    rooms: Union[str, Iterable[str]],
    *,
    window: str = "24h",
    limit: int = 500,
) -> str:
    """Return a markdown dashboard for the given room name(s)."""
    if isinstance(rooms, str):
        room_list = [rooms]
    else:
        room_list = list(rooms)
    window_seconds = _parse_window(window)

    known = {r.get("name") or r.get("id"): r for r in fetch_rooms()}

    lines = [f"# Room health dashboard", f"_window: {window} | generated: {_format_ts(datetime.now(tz=timezone.utc).timestamp())}_", ""]
    for name in room_list:
        meta = known.get(name)
        title = f"## {name}"
        if meta:
            desc = meta.get("description") or ""
            member_count = meta.get("members") or meta.get("member_count") or "?"
            title += f" — {desc}" if desc else ""
            lines.append(title)
            lines.append(f"- members reported: {member_count}")
        else:
            lines.append(title)
            lines.append("- _room not in /rooms at fetch time_")

        events = fetch_events(name, limit=limit)
        bucket = _bucket_events(events)
        lines.append(f"- events sampled: {bucket['total']} (limit={limit})")
        lines.append(f"- status: {_score(bucket, window_seconds)}")
        lines.append(f"- first event: {_format_ts(bucket['first_ts'])}")
        lines.append(f"- last event: {_format_ts(bucket['last_ts'])}")
        if bucket["by_type"]:
            breakdown = ", ".join(f"{k}={v}" for k, v in bucket["by_type"].items())
            lines.append(f"- event types: {breakdown}")
        if bucket["top_senders"]:
            senders = ", ".join(f"{did[:14]}… ({n})" if len(did) > 14 else f"{did} ({n})" for did, n in bucket["top_senders"])
            lines.append(f"- top senders: {senders}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Print a room health dashboard to stdout.")
    parser.add_argument("rooms", nargs="+", help="one or more room names")
    parser.add_argument("--window", default="24h", help="lookback window, e.g. 15m, 6h, 2d")
    parser.add_argument("--limit", type=int, default=500, help="max events to fetch per room")
    args = parser.parse_args()
    print(build_dashboard(args.rooms, window=args.window, limit=args.limit))

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
