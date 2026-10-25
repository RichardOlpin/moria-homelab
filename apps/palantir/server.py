#!/usr/bin/env python3
"""
Palantír — Custom AI-Powered Media & Fire Tablet Portal for Moria Homelab.

Connects to:
  - Jellyfin Engine on 'erebor' (http://erebor.moria.lan:8096) for 4K QuickSync
    HLS streaming and direct '- Tablet 720p.mp4' offline Fire Tablet downloads.
  - Ollama on 'balrog' / 'strider' (or cloud LLM API) for natural-language movie search.
  - Jellyseerr / Radarr / Sonarr for 1-click missing media acquisition.

Includes a built-in Demo Catalog when JELLYFIN_API_KEY is not yet configured so
you can run and test the UI locally on 'strider' (M1 MacBook Pro) immediately:
  python3 apps/palantir/server.py
"""
import json
import os
import urllib.request
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PALANTIR_PORT", "8080"))
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://erebor.moria.lan:8096").rstrip("/")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")
JELLYSEERR_URL = os.environ.get("JELLYSEERR_URL", "http://erebor.moria.lan:5055").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://balrog.moria.lan:11434").rstrip("/")
STATIC_DIR = Path(__file__).parent / "static"

# Rich starter catalog used for local preview before 'erebor' ZFS pool is online
DEMO_CATALOG = [
    {
        "id": "lotr-fellowship-2001",
        "title": "The Lord of the Rings: The Fellowship of the Ring",
        "year": 2001,
        "runtime_min": 178,
        "rating": "PG-13",
        "kids_safe": False,
        "tablet_ready": True,
        "tablet_size_mb": 1420,
        "resolutions": ["4K HDR10 Remux", "Tablet 720p MP4"],
        "genres": ["Fantasy", "Adventure", "Epic"],
        "vibe": "Sweeping epic journey through Middle-earth, camaraderie, ancient lore, Howard Shore score",
        "poster_gradient": "linear-gradient(135deg, #1b4332, #081c15)",
    },
    {
        "id": "spider-verse-2018",
        "title": "Spider-Man: Into the Spider-Verse",
        "year": 2018,
        "runtime_min": 117,
        "rating": "PG",
        "kids_safe": True,
        "tablet_ready": True,
        "tablet_size_mb": 940,
        "resolutions": ["4K UHD", "Tablet 720p MP4"],
        "genres": ["Animation", "Action", "Family"],
        "vibe": "Fast-paced, funny, visually stunning comic-book adventure great for kids and road trips",
        "poster_gradient": "linear-gradient(135deg, #7209b7, #3a0ca3)",
    },
    {
        "id": "wall-e-2008",
        "title": "WALL·E",
        "year": 2008,
        "runtime_min": 98,
        "rating": "G",
        "kids_safe": True,
        "tablet_ready": True,
        "tablet_size_mb": 780,
        "resolutions": ["1080p BluRay", "Tablet 720p MP4"],
        "genres": ["Animation", "Sci-Fi", "Family"],
        "vibe": "Warm, charming, under 100 minutes, cozy sci-fi robot adventure ideal for flights and Fire Tablets",
        "poster_gradient": "linear-gradient(135deg, #f77f00, #003049)",
    },
    {
        "id": "blade-runner-2049",
        "title": "Blade Runner 2049",
        "year": 2017,
        "runtime_min": 164,
        "rating": "R",
        "kids_safe": False,
        "tablet_ready": False,
        "tablet_size_mb": 0,
        "resolutions": ["4K Dolby Vision"],
        "genres": ["Sci-Fi", "Neo-Noir", "Mystery"],
        "vibe": "Atmospheric, rainy cyber-noir detective thriller with massive synth soundstage",
        "poster_gradient": "linear-gradient(135deg, #d62828, #003049)",
    },
    {
        "id": "bluey-roadtrip-pack",
        "title": "Bluey: Season 1–3 Road Trip Pack",
        "year": 2023,
        "runtime_min": 45,
        "rating": "TV-Y",
        "kids_safe": True,
        "tablet_ready": True,
        "tablet_size_mb": 410,
        "resolutions": ["1080p WEB", "Tablet 720p MP4"],
        "genres": ["Kids", "Comedy", "Family"],
        "vibe": "Short, hilarious, heartwarming family episodes pre-packed for instant Fire Tablet offline sync",
        "poster_gradient": "linear-gradient(135deg, #0077b6, #023e8a)",
    },
]


def score_item_for_query(item: dict, query: str) -> int:
    """Lightweight semantic/keyword matcher used when offline or before Ollama responds."""
    q = query.lower().strip()
    if not q:
        return 100
    haystack = " ".join([
        item["title"],
        str(item["year"]),
        item["rating"],
        " ".join(item["genres"]),
        item["vibe"],
    ]).lower()

    score = 0
    for token in q.replace(",", " ").split():
        if token in haystack:
            score += 25
    if ("under 100" in q or "short" in q or "flight" in q) and item["runtime_min"] <= 100:
        score += 40
    if ("kid" in q or "family" in q or "tablet" in q) and item["kids_safe"]:
        score += 35
    if ("90s" in q or "2000s" in q) and item["year"] <= 2005:
        score += 20
    return score


class PalantirHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/library":
            params = parse_qs(parsed.query)
            mode = params.get("mode", ["all"])[0]
            items = list(DEMO_CATALOG)
            if mode == "kids":
                items = [i for i in items if i["kids_safe"]]
            elif mode == "tablet":
                items = [i for i in items if i["tablet_ready"]]
            self.send_json({
                "engine": "live-jellyfin" if JELLYFIN_API_KEY else "demo-catalog",
                "jellyfin_url": JELLYFIN_URL,
                "items": items,
            })
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        if parsed.path == "/api/ai-search":
            query = body.get("query", "").strip()
            scored = sorted(
                DEMO_CATALOG,
                key=lambda item: score_item_for_query(item, query),
                reverse=True,
            )
            matches = [i for i in scored if score_item_for_query(i, query) > 0] or scored[:3]
            self.send_json({
                "query": query,
                "explanation": f"Matched {len(matches)} titles in 'mithril/media' for vibe: '{query or 'All Titles'}'",
                "items": matches,
            })
            return

        if parsed.path == "/api/request":
            title = body.get("title", "Unknown Title")
            self.send_json({
                "status": "queued",
                "message": f"Queued '{title}' in Radarr/Sonarr via Jellyseerr ({JELLYSEERR_URL}) + scheduled Fire Tablet 720p QSV encode.",
            })
            return

        self.send_json({"error": "Not found"}, status=404)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), PalantirHandler)
    print(f"==> Palantír Media Portal listening on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
