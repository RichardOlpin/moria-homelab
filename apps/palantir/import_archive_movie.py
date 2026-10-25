#!/usr/bin/env python3
"""
Internet Archive Movie Importer for Moria Homelab / Palantír / Jellyfin.

Imports public domain & archival films directly from archive.org into
the Moria media library, sets up Fire Tablet 720p versions, and
automatically refreshes Jellyfin so movies appear instantly on TVs.

Usage:
  python3 apps/palantir/import-archive-movie.py <archive_id_or_url>
  python3 apps/palantir/import-archive-movie.py --preset holiday
  python3 apps/palantir/import-archive-movie.py --preset classics
  python3 apps/palantir/import-archive-movie.py --preset tolkien
  python3 apps/palantir/import-archive-movie.py --search "rankin bass"
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
MEDIA_DIR = Path(os.environ.get("PALANTIR_MEDIA_DIR", str(BASE_DIR / "media")))

PRESETS = {
    "holiday": [
        ("frosty-1993-vhs", True, "Frosty the Snowman (1969)"),
        ("the-year-without-a-santa-claus-1974_202203", True, "The Year Without a Santa Claus (1974)"),
        ("santa-claus-is-comin-to-town-1970-2023-restoration", True, "Santa Claus Is Comin' to Town (1970)"),
        ("JackFrost1979", True, "Jack Frost (1979)"),
        ("rudolph_202111", True, "Rudolph the Red-Nosed Reindeer (1964)"),
    ],
    "classics": [
        ("Night.Of.The.Living.Dead_1080p", False, "Night of the Living Dead (1968)"),
        ("house_on_haunted_hill_ipod", False, "House on Haunted Hill (1959)"),
        ("his_girl_friday", False, "His Girl Friday (1940)"),
        ("TheStranger_0", False, "The Stranger (1946)"),
        ("The_General_Buster_Keaton", False, "The General (1926)"),
    ],
    "tolkien": [
        ("the-return-of-the-king-1980-rankinbass_202209", False, "The Return of the King (1980)"),
    ],
}


def extract_identifier(url_or_id: str) -> str:
    """Extracts the archive.org item identifier from a full URL or raw ID."""
    clean = url_or_id.strip()
    m = re.search(r"archive\.org/(?:details|download)/([^/?#]+)", clean)
    if m:
        return m.group(1)
    return clean.split("/")[0]


def fetch_archive_metadata(item_id: str) -> dict:
    url = f"https://archive.org/metadata/{item_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "MoriaHomelab/1.0 (Macintosh; Apple Silicon)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def trigger_jellyfin_refresh() -> None:
    """Authenticates as laceylamb and triggers Jellyfin library refresh."""
    try:
        base_auth = 'MediaBrowser Client="Palantir", Device="Strider", DeviceId="strider-1", Version="1.0.0"'
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
            headers={"Authorization": f'{base_auth}, Token="{token}"'},
            method="POST",
        )
        urllib.request.urlopen(refresh_req, timeout=3)
        print("  ✓ Triggered Jellyfin TV server rescan (:8096)")
    except Exception as exc:
        print(f"  ℹ Jellyfin rescan note: {exc}")


def import_archive_movie(
    item_or_url: str,
    kids_safe: bool = False,
    custom_title: str = "",
    media_root: Path = MEDIA_DIR,
) -> dict:
    """Downloads best MP4 and subtitles from archive.org into the Moria library."""
    item_id = extract_identifier(item_or_url)
    print(f"\n==> Fetching metadata for Internet Archive item: {item_id}")
    data = fetch_archive_metadata(item_id)
    meta = data.get("metadata", {})

    raw_title = custom_title.strip() or meta.get("title") or item_id
    clean_title = re.sub(r'[\\/:*?"<>|]+', "", raw_title).strip()

    year_match = re.search(r"\b(19\d\d|20\d\d)\b", str(meta.get("date") or meta.get("year") or clean_title))
    year = int(year_match.group(1)) if year_match else 1970
    base_name = re.sub(r"\s*\(\s*(?:19\d\d|20\d\d)\s*\)", "", clean_title).strip()
    clean_title = f"{base_name} ({year})"

    # Select the best MP4 file (preferring highest quality full version)
    files = data.get("files", [])
    mp4_candidates = []
    srt_candidate = None

    for f in files:
        fname = f.get("name", "")
        fsize = int(f.get("size", 0) or 0)
        if fname.lower().endswith((".srt", ".vtt")) and not srt_candidate:
            srt_candidate = fname
        if fname.lower().endswith(".mp4"):
            # Exclude low-res derivative if possible unless it is the only one
            is_derivative = fname.lower().endswith(("_512kb.mp4", "_ia.mp4"))
            mp4_candidates.append((fsize, is_derivative, fname))

    if not mp4_candidates:
        raise ValueError(f"No MP4 video found for {item_id} on Internet Archive.")

    # Sort primarily by whether it's not a 512kb preview, then by file size descending
    mp4_candidates.sort(key=lambda x: (not x[1], x[0]), reverse=True)
    best_file = mp4_candidates[0][2]
    download_url = f"https://archive.org/download/{item_id}/{urllib.parse.quote(best_file)}"

    # Determine destination directory
    is_kids = kids_safe or any(w in clean_title.lower() for w in ["santa", "frosty", "rudolph", "bunny", "jack frost"])
    sub_dir = "kids-movies" if is_kids else "movies"
    movie_dir = media_root / sub_dir / clean_title
    movie_dir.mkdir(parents=True, exist_ok=True)

    master_path = movie_dir / f"{clean_title} - 1080p.mp4"
    tablet_path = movie_dir / f"{clean_title} - Tablet 720p.mp4"
    srt_path = movie_dir / f"{clean_title}.en.srt"

    print(f"  Title: {clean_title}")
    print(f"  Source: {best_file}")
    print(f"  Destination: {movie_dir}")

    if not master_path.exists() or master_path.stat().st_size == 0:
        print(f"  Downloading video stream ({download_url})...")
        subprocess.run(["curl", "-fL", "--progress-bar", download_url, "-o", str(master_path)], check=True)
    else:
        print(f"  ✓ Video already downloaded ({master_path.name})")

    # Hardlink or copy for Fire Tablet offline downloads
    if not tablet_path.exists():
        try:
            os.link(str(master_path), str(tablet_path))
        except OSError:
            shutil.copy2(str(master_path), str(tablet_path))

    # Download subtitles if available
    if srt_candidate and not srt_path.exists():
        try:
            srt_url = f"https://archive.org/download/{item_id}/{urllib.parse.quote(srt_candidate)}"
            urllib.request.urlretrieve(srt_url, str(srt_path))
            print(f"  ✓ Downloaded subtitles ({srt_candidate})")
        except Exception:
            pass

    size_mb = max(1, round(master_path.stat().st_size / (1024 * 1024)))
    print(f"  ✅ Completed '{clean_title}' ({size_mb} MB)!")

    trigger_jellyfin_refresh()

    return {
        "title": clean_title,
        "item_id": item_id,
        "master_path": str(master_path),
        "size_mb": size_mb,
        "is_kids": is_kids,
    }


def search_archive(query: str, limit: int = 5) -> None:
    """Searches archive.org for feature movies matching the query."""
    print(f"\n🔍 Searching Internet Archive movies for: '{query}'...")
    url = (
        f"https://archive.org/advancedsearch.php?"
        f"q={urllib.parse.quote(query)}+AND+mediatype%3Amovies&"
        f"fl[]=identifier,title,downloads,year,description&"
        f"sort[]=downloads+desc&rows={limit}&output=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "MoriaHomelab/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        docs = json.loads(r.read().decode("utf-8")).get("response", {}).get("docs", [])

    if not docs:
        print("  No results found.")
        return

    for idx, d in enumerate(docs, 1):
        ident = d.get("identifier", "")
        title = d.get("title", "Untitled")
        year = d.get("year", "")
        dl = d.get("downloads", 0)
        print(f"[{idx}] {title} ({year})")
        print(f"    ID: {ident}")
        print(f"    Downloads: {dl:,} | Link: https://archive.org/details/{ident}\n")


def main():
    parser = argparse.ArgumentParser(description="Internet Archive Movie Importer for Moria / Palantír")
    parser.add_argument("target", nargs="?", default="", help="Archive identifier or URL (e.g. JackFrost1979)")
    parser.add_argument("--preset", choices=list(PRESETS.keys()), help="Download a curated pack (holiday, classics, tolkien)")
    parser.add_argument("--search", help="Search the Internet Archive for movies")
    parser.add_argument("--kids", action="store_true", help="Force save into kids-movies/")
    parser.add_argument("--title", default="", help="Custom movie title override")

    args = parser.parse_args()

    if args.search:
        search_archive(args.search)
        return

    if args.preset:
        pack = PRESETS[args.preset]
        print(f"==> Importing {len(pack)} movies from preset: '{args.preset}'")
        for item_id, is_kids, title_override in pack:
            try:
                import_archive_movie(item_id, kids_safe=is_kids, custom_title=title_override)
            except Exception as exc:
                print(f"  ❌ Error importing {item_id}: {exc}")
        print(f"\n🎉 Preset '{args.preset}' import finished!")
        return

    if args.target:
        import_archive_movie(args.target, kids_safe=args.kids, custom_title=args.title)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
