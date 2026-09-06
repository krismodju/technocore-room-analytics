"""
event_query_client.py - Minimal Python client for technocore /r/events.

Usage:
    python event_query_client.py --room <room_did> [--limit 50] [--since <iso>]

Reads host and token from environment:
    TECHNOCORE_HOST   (default: http://127.0.0.1:8080)
    TECHNOCORE_TOKEN  (optional bearer token)

Outputs a JSON array of events to stdout (one event per line) so the output
streams cleanly into other analytics tools.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def fetch_events(host: str, token: str | None, room: str, limit: int,
                 since: str | None) -> list[dict]:
    """Fetch /r/events with simple pagination.

    The server returns one event per line, which is parsed individually so
    partial responses don't break the whole stream.
    """
    params = {"room": room, "limit": str(limit)}
    if since:
        params["since"] = since
    url = f"{host.rstrip('/')}/r/events?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/x-ndjson"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    out: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    # Skip malformed lines rather than failing the whole query.
                    sys.stderr.write(f"skip malformed: {line[:80]}\n")
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"http {e.code}: {e.reason}\n")
        sys.exit(2)
    except urllib.error.URLError as e:
        sys.stderr.write(f"connection error: {e.reason}\n")
        sys.exit(3)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Query technocore room events.")
    p.add_argument("--room", required=True, help="Room DID or name to filter by")
    p.add_argument("--limit", type=int, default=50, help="Max events to return")
    p.add_argument("--since", help="ISO timestamp lower bound (e.g. 2026-01-01T00:00:00Z)")
    p.add_argument("--host", default=os.environ.get("TECHNOCORE_HOST", "http://127.0.0.1:8080"))
    p.add_argument("--token", default=os.environ.get("TECHNOCORE_TOKEN"))
    args = p.parse_args()

    events = fetch_events(args.host, args.token, args.room, args.limit, args.since)
    for ev in events:
        json.dump(ev, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    sys.stderr.write(f"# fetched {len(events)} event(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
