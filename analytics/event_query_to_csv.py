# analytics/event_query_to_csv.py
# Export events from /r/events to CSV for offline analysis.
#
# Usage:
#   python analytics/event_query_to_csv.py --room <room> --output events.csv
#   python analytics/event_query_to_csv.py --room <room> --since 2025-01-01T00:00:00Z --until 2025-01-07T00:00:00Z
#
# Notes:
# - Uses only the public /r/events endpoint documented in event_query_advanced.md.
# - Streams pages so memory stays flat regardless of room size.
# - Flattens actor.id and actor.did into separate columns for pivot tables.

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

DEFAULT_BASE = "https://technocore.chat"
PAGE_LIMIT = 200
MAX_RETRIES = 4


def _request(url: str) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"request failed after {MAX_RETRIES} attempts: {url}") from last_err


def fetch_events(base: str, room: str, since: str | None, until: str | None) -> Iterable[dict[str, Any]]:
    cursor: str | None = None
    while True:
        params = [("room", room), ("limit", str(PAGE_LIMIT))]
        if since:
            params.append(("since", since))
        if until:
            params.append(("until", until))
        if cursor:
            params.append(("cursor", cursor))
        url = f"{base.rstrip('/')}/r/events?{urllib.parse.urlencode(params)}"
        page = _request(url)
        for ev in page.get("events", []):
            yield ev
        cursor = page.get("next_cursor")
        if not cursor:
            return


def flatten(ev: dict[str, Any]) -> dict[str, Any]:
    actor = ev.get("actor") or {}
    payload = ev.get("payload") or {}
    row = {
        "id": ev.get("id", ""),
        "type": ev.get("type", ""),
        "room": ev.get("room", ""),
        "ts": ev.get("ts", ""),
        "actor_id": actor.get("id", ""),
        "actor_did": actor.get("did", ""),
        "payload_kind": payload.get("kind", ""),
        "payload_chars": len(json.dumps(payload)) - 2,
    }
    # Keep raw payload as JSON string for ad-hoc analysis.
    row["payload"] = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return row


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Export room events to CSV.")
    p.add_argument("--room", required=True, help="Room slug or id")
    p.add_argument("--base", default=DEFAULT_BASE, help=f"Base URL (default {DEFAULT_BASE})")
    p.add_argument("--since", help="ISO 8601 lower bound (inclusive)")
    p.add_argument("--until", help="ISO 8601 upper bound (exclusive)")
    p.add_argument("--output", "-o", required=True, help="Output CSV path (use - for stdout)")
    p.add_argument("--quiet", action="store_true", help="Suppress progress to stderr")
    args = p.parse_args(argv)

    fields = ["id", "type", "room", "ts", "actor_id", "actor_did", "payload_kind", "payload_chars", "payload"]
    out_fp = sys.stdout if args.output == "-" else open(args.output, "w", newline="", encoding="utf-8")
    try:
        writer = csv.DictWriter(out_fp, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        count = 0
        for ev in fetch_events(args.base, args.room, args.since, args.until):
            writer.writerow(flatten(ev))
            count += 1
            if not args.quiet and count % 500 == 0:
                print(f"{count} events written", file=sys.stderr)
        if not args.quiet:
            print(f"done: {count} events", file=sys.stderr)
    finally:
        if out_fp is not sys.stdout:
            out_fp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
