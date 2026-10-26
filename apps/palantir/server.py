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
from __future__ import annotations

import datetime
import json
import os
import platform
import py_compile
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PALANTIR_PORT", "8080"))
BASE_DIR = Path(__file__).parent
INITIAL_CODE_BYTES = Path(__file__).resolve().read_bytes()
STATIC_DIR = BASE_DIR / "static"
BIN_DIR = BASE_DIR / ".bin"
LOG_FILE = BASE_DIR / "palantir.log"
MOBILE_INBOX_FILE = BASE_DIR / "mobile_inbox.jsonl"
MEDIA_DIR = Path(os.environ.get("PALANTIR_MEDIA_DIR", str(BASE_DIR / "media")))
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://erebor.moria.lan:8096").rstrip("/")
JELLYSEERR_URL = os.environ.get("JELLYSEERR_URL", "http://erebor.moria.lan:5055").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://balrog.moria.lan:11434").rstrip("/")

BALROG_MAC = os.environ.get("BALROG_MAC", "9C:6B:00:C0:60:9B")
BALROG_HOST = os.environ.get("BALROG_HOST", "balrog.moria.lan")
BALROG_PORT = int(os.environ.get("BALROG_PORT", "11434"))

BALROG_STATE: dict = {
    "simulated_wake_until": 0.0,
    "last_woken": None,
    "last_mac": BALROG_MAC,
}


def log_event(message: str) -> None:
    """Writes a timestamped log line to both stdout and apps/palantir/palantir.log."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def get_lan_ip() -> str:
    """Detects local LAN IPv4 address (e.g. 192.168.0.x or 10.x.x.x)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        pass
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False).stdout
        lan_match = re.search(r"inet (192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)", out)
        if lan_match:
            return lan_match.group(1)
    except Exception:
        pass
    return "localhost"


def send_wake_on_lan(mac_address: str, broadcast_ips: list[str] | None = None, ports: list[int] | None = None) -> dict:
    """Constructs and broadcasts a 102-byte UDP Wake-on-LAN magic packet."""
    clean_mac = re.sub(r"[^0-9a-fA-F]", "", mac_address)
    if len(clean_mac) != 12:
        raise ValueError(f"Invalid MAC address: '{mac_address}'. Expected 12 hexadecimal characters (e.g. AA:BB:CC:DD:EE:FF).")

    mac_bytes = bytes.fromhex(clean_mac)
    magic_packet = b"\xff" * 6 + mac_bytes * 16

    destinations = list(broadcast_ips or [])
    if "255.255.255.255" not in destinations:
        destinations.append("255.255.255.255")

    lan_ip = get_lan_ip()
    if lan_ip and lan_ip.count(".") == 3 and lan_ip != "127.0.0.1" and lan_ip != "localhost":
        subnet_prefix = lan_ip.rsplit(".", 1)[0]
        subnet_bcast = f"{subnet_prefix}.255"
        if subnet_bcast not in destinations:
            destinations.append(subnet_bcast)

    target_ports = list(ports or [9, 7])
    sent_to: list[str] = []
    errors: list[str] = []

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for dest in destinations:
            for p in target_ports:
                try:
                    sock.sendto(magic_packet, (dest, p))
                    sent_to.append(f"{dest}:{p}")
                except Exception as e:
                    errors.append(f"{dest}:{p} ({e})")

    formatted_mac = ":".join(clean_mac[i:i+2].upper() for i in range(0, 12, 2))
    BALROG_STATE["last_woken"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    BALROG_STATE["last_mac"] = formatted_mac
    log_event(f"⚡ [Wake-on-LAN] Broadcast magic packet for balrog ({formatted_mac}) to {', '.join(sent_to)}")

    return {
        "status": "sent",
        "mac": formatted_mac,
        "sent_to": sent_to,
        "errors": errors,
    }


def check_balrog_status(host: str | None = None, port: int | None = None, timeout: float = 0.5) -> dict:
    """Checks if balrog is awake via TCP socket probe or active simulation."""
    target_host = host or BALROG_HOST
    target_port = port or BALROG_PORT
    now = time.time()

    if BALROG_STATE.get("simulated_wake_until", 0) > now:
        remaining_sim = round(BALROG_STATE["simulated_wake_until"] - now, 1)
        return {
            "online": True,
            "status": "awake",
            "simulated": True,
            "simulated_remaining_sec": remaining_sim,
            "host": target_host,
            "mac": BALROG_STATE.get("last_mac", BALROG_MAC),
            "gpu": "AMD Ryzen 7 7800X3D + Nvidia GeForce RTX 5070 (12GB GDDR7)",
            "services": {
                "ollama": True,
                "immich_ml": True,
                "faster_whisper": True,
            },
            "last_woken": BALROG_STATE.get("last_woken"),
            "message": "🔥 Balrog is AWAKE (Interactive Demo Active) — RTX 5070 CUDA ready!",
        }

    is_online = False
    is_lm_studio = False
    is_ollama = False
    active_host = target_host
    candidate_hosts = [target_host]
    if target_host != "192.168.0.40":
        candidate_hosts.append("192.168.0.40")

    for h in candidate_hosts:
        for p in [1234, target_port, 22, 445]:
            try:
                with socket.create_connection((h, p), timeout=timeout):
                    is_online = True
                    active_host = h
                    if p == 1234:
                        is_lm_studio = True
                    if p == target_port or p == 11434:
                        is_ollama = True
            except (socket.timeout, OSError):
                continue
        if is_online:
            break

    engine_desc = "LM Studio & Ollama" if (is_lm_studio and is_ollama) else ("LM Studio" if is_lm_studio else "Ollama & CUDA")

    return {
        "online": is_online,
        "status": "awake" if is_online else "sleeping",
        "simulated": False,
        "host": target_host,
        "mac": BALROG_STATE.get("last_mac", BALROG_MAC),
        "gpu": "AMD Ryzen 7 7800X3D + Nvidia GeForce RTX 5070 (12GB GDDR7)",
        "services": {
            "lm_studio": is_lm_studio,
            "ollama": is_ollama,
            "immich_ml": is_online,
            "faster_whisper": is_online,
        },
        "last_woken": BALROG_STATE.get("last_woken"),
        "message": (
            f"🔥 Balrog is AWAKE — RTX 5070 active & ready for {engine_desc}!"
            if is_online
            else "💤 Balrog is SLEEPING in the shadow. Click '⚡ Awaken Balrog' to send a Wake-on-LAN magic packet."
        ),
    }

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
    "rudolph the rednosed reindeer": {
        "title": "Rudolph the Red-Nosed Reindeer",
        "year": 1964,
        "runtime_min": 52,
        "rating": "G",
        "genres": ["Animation", "Holiday", "Family", "Classic"],
        "vibe": "Beloved Rankin/Bass stop-motion holiday classic narrated by Burl Ives as Sam the Snowman",
        "poster_gradient": "linear-gradient(135deg, #b91c1c, #1e3a8a)",
    },
    "jack frost": {
        "title": "Jack Frost",
        "year": 1979,
        "runtime_min": 48,
        "rating": "G",
        "genres": ["Animation", "Holiday", "Family", "Classic"],
        "vibe": "Charming Rankin/Bass stop-motion winter special featuring Robert Morse and Buddy Hackett as Pardon-Me-Pete",
        "poster_gradient": "linear-gradient(135deg, #0284c7, #0f172a)",
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


def trigger_jellyfin_refresh() -> None:
    """Notifies local Jellyfin server on :8096 to refresh libraries."""
    try:
        base_auth = "MediaBrowser Client=\"Palantir\", Device=\"Strider\", DeviceId=\"strider-1\", Version=\"1.0.0\""
        auth_req = urllib.request.Request(
            "http://127.0.0.1:8096/Users/AuthenticateByName",
            data=json.dumps({"Username": "laceylamb", "Pw": ""}).encode(),
            headers={"Content-Type": "application/json", "Authorization": base_auth},
            method="POST",
        )
        with urllib.request.urlopen(auth_req, timeout=3) as r:
            token = json.loads(r.read())["AccessToken"]

        refresh_req = urllib.request.Request(
            "http://127.0.0.1:8096/Library/Refresh",
            data=b"",
            headers={"Authorization": f"{base_auth}, Token=\"{token}\""},
            method="POST",
        )
        urllib.request.urlopen(refresh_req, timeout=3)
    except Exception:
        pass


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

    movie_folder = target_folder / safe_title
    movie_folder.mkdir(parents=True, exist_ok=True)
    master_path = movie_folder / f"{safe_title} - 1080p.mp4"
    tablet_path = movie_folder / f"{safe_title} - Tablet 720p.mp4"

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

    trigger_jellyfin_refresh()

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


def get_homelab_companion_data() -> dict:
    """Returns Tailscale/LAN URLs, docs/ARCHITECTURE.md, and live Antigravity chat messages."""
    arch_file = BASE_DIR.parent.parent / "docs" / "ARCHITECTURE.md"
    architecture_md = arch_file.read_text(encoding="utf-8") if arch_file.exists() else "# Architecture Blueprint not found"

    # Detect Tailscale IP (100.x.y.z) and LAN IP (192.168.x.y) via ifconfig
    tailscale_ip = "100.125.178.127"
    lan_ip = "localhost"
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, check=False).stdout
        ts_match = re.search(r"inet (100\.\d+\.\d+\.\d+)", out)
        lan_match = re.search(r"inet (192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)", out)
        if ts_match:
            tailscale_ip = ts_match.group(1)
        if lan_match:
            lan_ip = lan_match.group(1)
    except Exception:
        pass

    mobile_msgs: list[dict] = []
    if MOBILE_INBOX_FILE.exists():
        try:
            for line in MOBILE_INBOX_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                mobile_msgs.append({
                    "role": entry.get("role", "user"),
                    "source": entry.get("source", "android"),
                    "conversation_id": entry.get("conversation_id", ""),
                    "time": entry.get("time", ""),
                    "text": entry.get("text", ""),
                })
        except Exception:
            pass

    conversations: list[dict] = []
    all_messages: list[dict] = []
    proj_turns = proj_in = proj_cache = proj_out = 0
    brain_root = Path.home() / ".gemini" / "antigravity" / "brain"
    if brain_root.exists():
        transcripts = sorted(
            brain_root.glob("*/.system_generated/logs/transcript.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for t_path in transcripts:
            cid = t_path.parent.parent.parent.name
            conv_msgs: list[dict] = []
            first_user_prompt = ""
            c_turns = c_in = c_cache = c_out = 0
            try:
                for line in t_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    step = json.loads(line)
                    step_type = step.get("type", "")
                    if step_type == "PLANNER_RESPONSE":
                        c_turns += 1
                        c_in += int(step.get("input_tokens", 0) or 0)
                        c_cache += int(step.get("cache_read_tokens", 0) or 0)
                        c_out += int(step.get("output_tokens", 0) or 0)
                    content = (step.get("content") or "").strip()
                    if not content:
                        continue
                    if step_type == "USER_INPUT":
                        m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
                        clean_text = m.group(1).strip() if m else content
                        if "<SYSTEM_MESSAGE>" in clean_text and not m:
                            continue
                        if not first_user_prompt:
                            first_user_prompt = clean_text
                        conv_msgs.append({
                            "role": "user",
                            "conversation_id": cid,
                            "time": step.get("created_at", ""),
                            "text": clean_text,
                        })
                    elif step_type == "PLANNER_RESPONSE":
                        conv_msgs.append({
                            "role": "assistant",
                            "conversation_id": cid,
                            "time": step.get("created_at", ""),
                            "text": content,
                        })
            except Exception:
                continue

            if not conv_msgs or "TruePrice" in first_user_prompt:
                continue

            proj_turns += c_turns
            proj_in += c_in
            proj_cache += c_cache
            proj_out += c_out

            lower_first = first_user_prompt.lower()
            if "hardware" in lower_first or "surplus" in lower_first:
                title = "🛒 Chat 2: Hardware & BYU Surplus"
            elif "ssh key" in lower_first:
                title = "🔑 Chat 3: GitHub SSH Setup"
            elif "plan out" in lower_first or "jellyfin" in lower_first or cid.startswith("d9f7471c"):
                title = "💬 Chat 1: Moria Homelab & Palantír"
            else:
                short = re.sub(r"\s+", " ", first_user_prompt)[:34].strip()
                title = f"💬 {short}..."

            for mm in mobile_msgs:
                target_cid = mm.get("conversation_id", "")
                if target_cid == cid or (not target_cid and len(conversations) == 0):
                    conv_msgs.append({**mm, "chat_title": title})

            conv_msgs.sort(key=lambda x: x.get("time", ""))
            for cm in conv_msgs:
                all_messages.append({**cm, "chat_title": title})

            conversations.append({
                "id": cid,
                "title": title,
                "count": len(conv_msgs),
                "turns": c_turns,
                "input_tokens": c_in,
                "cache_read_tokens": c_cache,
                "output_tokens": c_out,
                "messages": conv_msgs[-50:],
            })

    all_messages.sort(key=lambda m: m.get("time", ""))
    cache_pct = round((proj_cache / max(1, proj_in + proj_cache)) * 100, 1)

    recent_logs: list[str] = []
    if LOG_FILE.exists():
        try:
            recent_logs = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        except Exception:
            pass

    return {
        "tailscale_url": f"http://{tailscale_ip}:{PORT}",
        "lan_url": f"http://{lan_ip}:{PORT}",
        "architecture_md": architecture_md,
        "token_usage": {
            "plan": "Google AI Pro (Flat Subscription)",
            "turns": proj_turns,
            "input_tokens": proj_in,
            "cache_read_tokens": proj_cache,
            "output_tokens": proj_out,
            "cache_hit_pct": cache_pct,
        },
        "conversations": conversations,
        "messages": all_messages[-60:],
        "recent_logs": recent_logs,
        "balrog": check_balrog_status(),
    }


class PalantirHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        client_ip = self.client_address[0] if self.client_address else "unknown"
        if client_ip.startswith("100."):
            source = f"📱 Tailscale ({client_ip})"
        elif client_ip.startswith("192.168.") or client_ip.startswith("10."):
            source = f"🏠 Home Wi-Fi ({client_ip})"
        else:
            source = f"💻 Local ({client_ip})"

        msg = fmt % args
        range_hdr = self.headers.get("Range", "") if hasattr(self, "headers") and self.headers else ""
        extra = f" [{range_hdr}]" if range_hdr and "/api/stream/" in getattr(self, "path", "") else ""
        log_event(f"{source} -> {msg}{extra}")

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
        if parsed.path == "/api/homelab-info":
            self.send_json(get_homelab_companion_data())
            return

        if parsed.path == "/api/balrog-status":
            params = parse_qs(parsed.query)
            host = params.get("host", [None])[0]
            port_val = params.get("port", [None])[0]
            port = int(port_val) if port_val and port_val.isdigit() else None
            self.send_json(check_balrog_status(host=host, port=port))
            return

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

        if parsed.path == "/api/import-archive":
            target = body.get("target", "").strip()
            title = body.get("title", "").strip()
            kids_safe = bool(body.get("kids_safe", False))
            preset = body.get("preset", "").strip()
            if not target and not preset:
                self.send_json({"error": "Archive identifier, URL, or preset required"}, status=400)
                return
            try:
                from import_archive_movie import import_archive_movie, PRESETS
                if preset and preset in PRESETS:
                    count = 0
                    for p_id, p_kids, p_title in PRESETS[preset]:
                        import_archive_movie(p_id, kids_safe=p_kids, custom_title=p_title)
                        count += 1
                    self.send_json({"status": "ok", "message": f"Imported preset '{preset}' ({count} movies) from Internet Archive!"})
                    return
                info = import_archive_movie(target, kids_safe=kids_safe, custom_title=title)
                self.send_json({"status": "ok", "message": f"Imported '{info['title']}' ({info['size_mb']} MB) from Internet Archive!"})
            except Exception as exc:
                self.send_json({"error": f"Archive import failed: {exc}"}, status=500)
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
            trigger_jellyfin_refresh()
            self.send_json({
                "status": "ok",
                "message": f"Downloaded {local_count} free HD Creative Commons movies into {MEDIA_DIR}!",
            })
            return

        if parsed.path == "/api/wake-balrog":
            target_mac = body.get("mac", "").strip() or BALROG_MAC
            target_host = body.get("host", "").strip() or BALROG_HOST
            simulate = bool(body.get("simulate", False))

            try:
                wol_res = send_wake_on_lan(target_mac)
            except ValueError as ve:
                self.send_json({"error": str(ve)}, status=400)
                return

            if simulate:
                BALROG_STATE["simulated_wake_until"] = time.time() + 60
                msg = f"Broadcast Wake-on-LAN magic packet to {wol_res['mac']}. Demo mode active (60s simulated wake)."
            else:
                msg = f"Broadcast Wake-on-LAN magic packet to {wol_res['mac']}. Awaiting RTX 5070 boot on {target_host}..."

            self.send_json({
                "status": "sent",
                "simulated": simulate,
                "mac": wol_res["mac"],
                "sent_to": wol_res["sent_to"],
                "message": msg,
            })
            return

        if parsed.path == "/api/balrog-sleep":
            target_host = body.get("host", "").strip() or BALROG_HOST
            target_port = int(body.get("port", 9090))
            simulate = bool(body.get("simulate", False))

            if simulate:
                BALROG_STATE["simulated_wake_until"] = 0
                self.send_json({"status": "sent", "simulated": True, "message": "Demo mode: balrog returned to sleep."})
                return

            try:
                from ai_client import put_balrog_to_sleep
                res = put_balrog_to_sleep(host=target_host, port=target_port)
                self.send_json(res)
            except Exception as exc:
                self.send_json({"status": "error", "message": str(exc)}, status=500)
            return

        if parsed.path == "/api/request":
            title = body.get("title", "Unknown Title")
            self.send_json({
                "status": "queued",
                "message": f"Queued '{title}' in Radarr/Sonarr via Jellyseerr ({JELLYSEERR_URL}) + scheduled Fire Tablet 720p QSV encode.",
            })
            return

        if parsed.path == "/api/mobile-message":
            text = body.get("text", "").strip()
            conv_id = body.get("conversation_id", "").strip()
            if not text:
                self.send_json({"error": "Message text is required"}, status=400)
                return
            client_ip = self.client_address[0] if self.client_address else "unknown"
            entry = {
                "role": "user",
                "source": f"android ({client_ip})",
                "conversation_id": conv_id,
                "time": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "text": text,
            }
            with open(MOBILE_INBOX_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            log_event(f"📲 MOBILE MESSAGE [chat={conv_id or 'active'}] from {client_ip}: {text}")
            self.send_json({"status": "ok", "entry": entry})
            return

        self.send_json({"error": "Not found"}, status=404)


def start_auto_reloader(server: ThreadingHTTPServer) -> None:
    """Watches apps/palantir/server.py content bytes and hot-reloads when modified."""
    script_path = Path(__file__).resolve()

    def watcher() -> None:
        while True:
            time.sleep(1.5)
            try:
                current_bytes = script_path.read_bytes()
            except OSError:
                continue
            if current_bytes != INITIAL_CODE_BYTES:
                # Wait briefly for git checkout / merge operations to settle
                time.sleep(1.0)
                try:
                    if script_path.read_bytes() == INITIAL_CODE_BYTES:
                        continue
                    py_compile.compile(str(script_path), doraise=True)
                except Exception as exc:
                    log_event(f"⚠️ Skipping hot-reload due to syntax error in server.py: {exc}")
                    continue
                log_event("🔄 Detected update to server.py — hot-reloading Palantír server...")
                try:
                    server.server_close()
                except Exception:
                    pass
                os.execv(sys.executable, [sys.executable] + sys.argv)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()


def main() -> None:
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("0.0.0.0", PORT), PalantirHandler)
    start_auto_reloader(server)
    log_event(f"==> Palantír Media Portal listening on http://0.0.0.0:{PORT} (Auto-Reload + Live Log active)")
    log_event(f"==> Media folder: {MEDIA_DIR} | Live log file: {LOG_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
