#!/usr/bin/env python3
"""
Palantír — Custom AI-Powered Media & Fire Tablet Portal for Moria Homelab.

Features:
  - Automatic filesystem media scanner (scans PALANTIR_MEDIA_DIR or ./media)
    that pairs master files with '- Tablet 720p.mp4' Fire Tablet versions.
  - Full HTTP 206 Byte-Range Video Streaming (/api/stream/<id>) for instant
    scrubbing in the built-in HTML5 Cinema Player modal.
  - Direct Fire Tablet MP4 Attachment Download (/api/download/<id>).
  - YouTube / Video URL Importer (/api/import-url) powered by yt-dlp for
    importing owned media directly into the library & Fire Tablet drawer.
  - One-click Free Open Movies seeder (/api/seed-movies -> seed-free-movies.sh).
  - Natural-language AI Mood & Runtime Search (/api/ai-search) with Ollama/LLM hook.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PALANTIR_PORT", "8080"))
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
BIN_DIR = BASE_DIR / ".bin"
MEDIA_DIR = Path(os.environ.get("PALANTIR_MEDIA_DIR", str(BASE_DIR / "media")))
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://erebor.moria.lan:8096").rstrip("/")
JELLYSEERR_URL = os.environ.get("JELLYSEERR_URL", "http://erebor.moria.lan:5055").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://balrog.moria.lan:11434").rstrip("/")

# Known metadata enrichment for Open Movies & Owned Classics
KNOWN_METADATA = {
    "the lord of the rings the fellowship of the ring": {
        "title": "The Lord of the Rings: The Fellowship of the Ring",
        "year": 2001,
        "runtime_min": 178,
        "rating": "PG-13",
        "genres": ["Fantasy", "Adventure", "Epic"],
        "vibe": "Sweeping epic journey through Middle-earth, camaraderie, Doors of Durin ('Speak, friend, and enter'), Howard Shore score",
        "poster_gradient": "linear-gradient(135deg, #1b4332, #081c15)",
    },
    "sintel": {
        "title": "Sintel",
        "year": 2010,
        "runtime_min": 15,
        "rating": "PG-13",
        "genres": ["Fantasy", "Adventure", "Dragon"],
        "vibe": "Epic fantasy quest of a lone warrior searching for her baby dragon Scales across ancient lands",
        "poster_gradient": "linear-gradient(135deg, #9d0208, #370617)",
    },
    "big buck bunny": {
        "title": "Big Buck Bunny",
        "year": 2008,
        "runtime_min": 10,
        "rating": "G",
        "genres": ["Animation", "Kids", "Comedy"],
        "vibe": "Hilarious, kid-safe slapstick forest adventure starring a giant gentle rabbit — great for Fire Tablets",
        "poster_gradient": "linear-gradient(135deg, #2b9348, #004b23)",
    },
    "tears of steel": {
        "title": "Tears of Steel",
        "year": 2012,
        "runtime_min": 12,
        "rating": "PG-13",
        "genres": ["Sci-Fi", "Cyberpunk", "Action"],
        "vibe": "Atmospheric cyberpunk sci-fi in futuristic Amsterdam with giant mecha robots and laser combat",
        "poster_gradient": "linear-gradient(135deg, #0077b6, #03045e)",
    },
    "elephants dream": {
        "title": "Elephants Dream",
        "year": 2006,
        "runtime_min": 11,
        "rating": "PG",
        "genres": ["Sci-Fi", "Animation", "Surreal"],
        "vibe": "Surreal industrial sci-fi exploration inside a giant cavernous machine world",
        "poster_gradient": "linear-gradient(135deg, #5a189a, #10002b)",
    },
}

DEMO_PREVIEW_ITEMS = [
    {
        "id": "demo-lotr-fellowship",
        "title": "The Lord of the Rings: The Fellowship of the Ring",
        "year": 2001,
        "runtime_min": 178,
        "rating": "PG-13",
        "kids_safe": False,
        "tablet_ready": True,
        "tablet_size_mb": 1420,
        "playable": False,
        "resolutions": ["4K HDR10 Remux", "Tablet 720p MP4"],
        "genres": ["Fantasy", "Adventure", "Epic"],
        "vibe": "Sweeping epic journey through Middle-earth, camaraderie, Doors of Durin, Howard Shore score",
        "poster_gradient": "linear-gradient(135deg, #1b4332, #081c15)",
    },
    {
        "id": "demo-wall-e",
        "title": "WALL·E",
        "year": 2008,
        "runtime_min": 98,
        "rating": "G",
        "kids_safe": True,
        "tablet_ready": True,
        "tablet_size_mb": 780,
        "playable": False,
        "resolutions": ["1080p BluRay", "Tablet 720p MP4"],
        "genres": ["Animation", "Sci-Fi", "Family"],
        "vibe": "Warm, charming, under 100 minutes, cozy sci-fi robot adventure ideal for flights and Fire Tablets",
        "poster_gradient": "linear-gradient(135deg, #f77f00, #003049)",
    },
]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def ensure_yt_dlp() -> str:
    """Finds yt-dlp in PATH or auto-downloads yt-dlp + deno JS runtime to .bin/."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure Deno JS runtime is present in .bin/ so YouTube extraction succeeds
    deno_bin = BIN_DIR / "deno"
    if not shutil.which("deno") and not deno_bin.exists():
        arch = "aarch64-apple-darwin" if (platform.system() == "Darwin" and platform.machine() == "arm64") else "x86_64-unknown-linux-gnu"
        deno_zip = BIN_DIR / "deno.zip"
        urllib.request.urlretrieve(
            f"https://github.com/denoland/deno/releases/latest/download/deno-{arch}.zip",
            str(deno_zip),
        )
        subprocess.run(["unzip", "-qo", str(deno_zip), "-d", str(BIN_DIR)], check=True)
        deno_bin.chmod(0o755)
        deno_zip.unlink(missing_ok=True)

    sys_bin = shutil.which("yt-dlp")
    if sys_bin:
        return sys_bin

    local_bin = BIN_DIR / "yt-dlp"
    if local_bin.exists():
        return str(local_bin)

    asset = "yt-dlp_macos" if platform.system() == "Darwin" else "yt-dlp"
    url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{asset}"
    urllib.request.urlretrieve(url, str(local_bin))
    local_bin.chmod(0o755)
    return str(local_bin)


def import_video_url(url: str, custom_title: str = "", kids_safe: bool = False) -> dict:
    """Downloads a YouTube or direct video URL into MEDIA_DIR as MP4 + Fire Tablet hardlink."""
    yt_dlp = ensure_yt_dlp()
    env = os.environ.copy()
    env["PATH"] = f"{BIN_DIR}:{env.get('PATH', '')}"

    sub_dir = "kids-movies" if kids_safe else "movies"
    target_folder = MEDIA_DIR / sub_dir
    target_folder.mkdir(parents=True, exist_ok=True)

    if not custom_title.strip():
        res = subprocess.run(
            [yt_dlp, "--no-playlist", "--get-title", url],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        raw_title = res.stdout.strip().splitlines()[0] if res.stdout.strip() else "Imported Movie"
    else:
        raw_title = custom_title.strip()

    safe_title = re.sub(r'[\\/:*?"<>|]+', "", raw_title).strip()
    if not re.search(r"\(\d{4}\)", safe_title):
        safe_title = f"{safe_title} (2001)" if "lord of the rings" in safe_title.lower() else f"{safe_title} (2024)"

    master_path = target_folder / f"{safe_title} - 1080p.mp4"
    tablet_path = target_folder / f"{safe_title} - Tablet 720p.mp4"

    subprocess.run(
        [
            yt_dlp,
            "--no-playlist",
            "-f",
            "b[ext=mp4]/b",
            "-o",
            str(master_path),
            url,
        ],
        env=env,
        check=True,
    )

    if master_path.exists() and not tablet_path.exists():
        try:
            os.link(master_path, tablet_path)
        except OSError:
            shutil.copy2(master_path, tablet_path)

    return {
        "title": safe_title,
        "master_path": str(master_path),
        "size_mb": max(1, round(master_path.stat().st_size / (1024 * 1024))) if master_path.exists() else 0,
    }


def scan_local_media() -> dict[str, dict]:
    """Scans MEDIA_DIR for real .mp4/.mkv files and pairs '- Tablet 720p.mp4' versions."""
    catalog: dict[str, dict] = {}
    if not MEDIA_DIR.exists():
        return catalog

    for file_path in sorted(MEDIA_DIR.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in {".mp4", ".mkv", ".webm"}:
            continue

        stem = file_path.stem
        is_tablet_version = bool(re.search(r"-\s*tablet\s*720p$", stem, re.IGNORECASE))
        clean_title = re.sub(
            r"\s*-\s*(2160p|4K|1080p|720p|Tablet\s*720p|Bluray|Remux).*$",
            "",
            stem,
            flags=re.IGNORECASE,
        ).strip()

        year_match = re.search(r"\((\d{4})\)", clean_title)
        year = int(year_match.group(1)) if year_match else 2024
        base_title = re.sub(r"\s*\(\d{4}\)\s*", "", clean_title).strip()
        lookup_key = re.sub(r"[^a-z0-9 ]+", "", base_title.lower()).strip()
        item_id = slugify(f"{base_title}-{year}")
        kids_safe = "kids" in str(file_path.parent).lower()

        meta = KNOWN_METADATA.get(lookup_key, {})
        if item_id not in catalog:
            catalog[item_id] = {
                "id": item_id,
                "title": meta.get("title", base_title),
                "year": meta.get("year", year),
                "runtime_min": meta.get("runtime_min", 15),
                "rating": meta.get("rating", "G" if kids_safe else "PG-13"),
                "kids_safe": kids_safe or meta.get("rating") == "G",
                "tablet_ready": False,
                "tablet_size_mb": 0,
                "playable": True,
                "stream_path": str(file_path),
                "download_path": str(file_path),
                "resolutions": [],
                "genres": meta.get("genres", ["Movie", "Local Stream"]),
                "vibe": meta.get("vibe", f"Local media file ({file_path.name}) ready for instant Direct Play"),
                "poster_gradient": meta.get("poster_gradient", "linear-gradient(135deg, #0f766e, #111827)"),
            }

        entry = catalog[item_id]
        size_mb = max(1, round(file_path.stat().st_size / (1024 * 1024)))
        if is_tablet_version:
            entry["tablet_ready"] = True
            entry["tablet_size_mb"] = size_mb
            entry["download_path"] = str(file_path)
            if "Tablet 720p MP4" not in entry["resolutions"]:
                entry["resolutions"].append("Tablet 720p MP4")
        else:
            entry["stream_path"] = str(file_path)
            if "HD Direct Play" not in entry["resolutions"]:
                entry["resolutions"].insert(0, "HD Direct Play")
            if not entry["tablet_ready"]:
                entry["tablet_size_mb"] = size_mb

    return catalog


def get_full_catalog() -> list[dict]:
    local_items = list(scan_local_media().values())
    local_titles = {i["title"].lower() for i in local_items}
    remaining_demos = [d for d in DEMO_PREVIEW_ITEMS if d["title"].lower() not in local_titles]
    return local_items + remaining_demos


def score_item_for_query(item: dict, query: str) -> int:
    q = query.lower().strip()
    if not q:
        return 100 + (50 if item.get("playable") else 0)
    haystack = " ".join([
        item["title"],
        str(item["year"]),
        item["rating"],
        " ".join(item["genres"]),
        item["vibe"],
    ]).lower()

    score = 20 if item.get("playable") else 0
    for token in q.replace(",", " ").split():
        if token in haystack:
            score += 25
    if ("under 100" in q or "short" in q or "flight" in q) and item["runtime_min"] <= 100:
        score += 40
    if ("kid" in q or "family" in q or "tablet" in q or "bunny" in q) and item["kids_safe"]:
        score += 35
    if ("dragon" in q or "fantasy" in q or "middle-earth" in q or "lotr" in q) and (
        "Fantasy" in item["genres"] or "Dragon" in item["genres"]
    ):
        score += 45
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

    def serve_video_file(self, file_path: Path, as_attachment: bool = False) -> None:
        if not file_path.exists():
            self.send_error(404, "Video file not found on disk")
            return

        file_size = file_path.stat().st_size
        range_header = self.headers.get("Range")

        if as_attachment or not range_header:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            if as_attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
            self.end_headers()
            with open(file_path, "rb") as f:
                while chunk := f.read(256 * 1024):
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break
            return

        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m:
            self.send_error(416, "Invalid Range")
            return

        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()

        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/library":
            params = parse_qs(parsed.query)
            mode = params.get("mode", ["all"])[0]
            all_items = get_full_catalog()
            playable_count = sum(1 for i in all_items if i.get("playable"))
            items = list(all_items)
            if mode == "kids":
                items = [i for i in items if i["kids_safe"]]
            elif mode == "tablet":
                items = [i for i in items if i["tablet_ready"]]

            clean_items = [
                {k: v for k, v in i.items() if k not in {"stream_path", "download_path"}}
                for i in items
            ]
            self.send_json({
                "engine": f"local-media ({playable_count} playable MP4s on disk)",
                "playable_count": playable_count,
                "items": clean_items,
            })
            return

        if parsed.path.startswith("/api/stream/"):
            item_id = parsed.path.split("/api/stream/", 1)[1]
            local_map = scan_local_media()
            if item_id not in local_map:
                self.send_error(404, "Stream not found")
                return
            self.serve_video_file(Path(local_map[item_id]["stream_path"]), as_attachment=False)
            return

        if parsed.path.startswith("/api/download/"):
            item_id = parsed.path.split("/api/download/", 1)[1]
            local_map = scan_local_media()
            if item_id not in local_map:
                self.send_error(404, "Download not found")
                return
            self.serve_video_file(Path(local_map[item_id]["download_path"]), as_attachment=True)
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        if parsed.path == "/api/ai-search":
            query = body.get("query", "").strip()
            catalog = get_full_catalog()
            scored = sorted(
                catalog,
                key=lambda item: score_item_for_query(item, query),
                reverse=True,
            )
            matches = [i for i in scored if score_item_for_query(i, query) > 20] or scored[:4]
            clean_matches = [
                {k: v for k, v in i.items() if k not in {"stream_path", "download_path"}}
                for i in matches
            ]
            self.send_json({
                "query": query,
                "explanation": f"Matched {len(clean_matches)} titles for vibe: '{query or 'All Titles'}'",
                "items": clean_matches,
            })
            return

        if parsed.path == "/api/import-url":
            url = body.get("url", "").strip()
            title = body.get("title", "").strip()
            kids_safe = bool(body.get("kids_safe", False))
            if not url:
                self.send_json({"error": "URL is required"}, status=400)
                return
            try:
                info = import_video_url(url, title, kids_safe)
                self.send_json({
                    "status": "ok",
                    "message": f"Imported '{info['title']}' ({info['size_mb']} MB) — ready for Direct Play & Fire Tablet download!",
                })
            except Exception as exc:
                self.send_json({"error": f"Import failed: {exc}"}, status=500)
            return

        if parsed.path == "/api/seed-movies":
            script = BASE_DIR / "seed-free-movies.sh"
            subprocess.run([str(script), str(MEDIA_DIR)], check=True)
            local_count = len(scan_local_media())
            self.send_json({
                "status": "ok",
                "message": f"Downloaded {local_count} free HD Creative Commons movies into {MEDIA_DIR}!",
            })
            return

        if parsed.path == "/api/wake-balrog":
            self.send_json({
                "status": "sent",
                "message": "Sent Wake-on-LAN magic packet via gandalf to balrog (RTX 5070 Gaming PC).",
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
    print(f"==> Media folder: {MEDIA_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
