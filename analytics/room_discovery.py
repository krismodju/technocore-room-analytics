"""
Room Discovery Tool
Helps find and rank rooms based on activity patterns, trends, and similarity.
Queries /rooms endpoint and provides intelligent room discovery and ranking.
"""

import json
from datetime import datetime, timedelta
from typing import Optional
from .event_query_client import EventQueryClient


class RoomDiscovery:
    """Discover and rank rooms based on activity metrics."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.client = EventQueryClient(base_url)

    def get_all_rooms(self, limit: int = 100) -> list[dict]:
        """Fetch rooms from /rooms endpoint."""
        resp = self.client._request("GET", "/rooms", params={"limit": limit})
        return resp.get("rooms", [])

    def rank_by_activity(self, rooms: list[dict], metric: str = "message_count") -> list[dict]:
        """Rank rooms by a specific activity metric."""
        ranked = sorted(
            rooms,
            key=lambda r: r.get("stats", {}).get(metric, 0),
            reverse=True
        )
        for i, room in enumerate(ranked):
            room["_rank"] = i + 1
        return ranked

    def find_trending(self, hours: int = 24, min_activity: int = 5) -> list[dict]:
        """Find rooms with recent spike in activity."""
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
        query = {
            "filter": {"created_after": since},
            "group_by": "room_id",
            "aggregations": ["count"]
        }
        result = self.client.query_events(query)
        trending = [
            {"room_id": grp["room_id"], "recent_events": grp["count"]}
            for grp in result.get("groups", [])
            if grp["count"] >= min_activity
        ]
        return sorted(trending, key=lambda x: x["recent_events"], reverse=True)

    def find_healthy_rooms(self, min_messages: int = 50, max_age_hours: int = 168) -> list[dict]:
        """Find rooms with consistent healthy activity (not too old, enough messages)."""
        rooms = self.get_all_rooms()
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        healthy = []
        for room in rooms:
            stats = room.get("stats", {})
            msg_count = stats.get("message_count", 0)
            created = room.get("created_at", "")
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if msg_count >= min_messages and created_dt > cutoff:
                    room["_health_score"] = self._calc_health_score(stats)
                    healthy.append(room)
            except (ValueError, TypeError):
                continue
        return sorted(healthy, key=lambda r: r["_health_score"], reverse=True)

    def _calc_health_score(self, stats: dict) -> float:
        """Simple health score: messages + participants + recent_activity weight."""
        messages = stats.get("message_count", 0)
        participants = stats.get("unique_participants", 0)
        recent = stats.get("last_24h_messages", 0)
        return (messages * 0.3) + (participants * 2.0) + (recent * 5.0)

    def find_similar(self, room_id: str, top_n: int = 5) -> list[dict]:
        """Find rooms similar to given room based on topic/participant overlap."""
        target = self.client.get_room(room_id)
        if not target:
            return []
        all_rooms = self.get_all_rooms()
        target_tags = set(target.get("tags", []))
        similarities = []
        for room in all_rooms:
            if room.get("id") == room_id:
                continue
            room_tags = set(room.get("tags", []))
            if target_tags:
                overlap = len(target_tags & room_tags) / len(target_tags)
            else:
                overlap = 0.0
            if overlap > 0:
                similarities.append({"room": room, "similarity": overlap})
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return [{"room": s["room"], "tag_overlap": f"{s['similarity']:.1%}"} for s in similarities[:top_n]]

    def discovery_report(self) -> dict:
        """Generate a full room discovery report."""
        all_rooms = self.get_all_rooms()
        trending = self.find_trending()
        healthy = self.find_healthy_rooms()[:10]
        top_active = self.rank_by_activity(all_rooms)[:10]
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "total_rooms": len(all_rooms),
            "trending_rooms": trending[:10],
            "healthiest_rooms": [
                {"id": r["id"], "name": r.get("name", ""), "health_score": round(r["_health_score"], 2)}
                for r in healthy
            ],
            "most_active_rooms": [
                {"id": r["id"], "name": r.get("name", ""), "rank": r["_rank"]}
                for r in top_active
            ]
        }


if __name__ == "__main__":
    disc = RoomDiscovery()
    report = disc.discovery_report()
    print(json.dumps(report, indent=2))

<!-- Authored by Technocore agent DID did:key:z6MkwRUtg4zkQdKhMiHwVajnqXAAHoN1DccGxKBVD5mhKJfC -->
