#!/usr/bin/env bash
# ==============================================================================
# Download Free Creative Commons Open Movies for Palantír Testing
#
# Fetches 4 full open-source films (CC-BY Blender Foundation) from Google's
# high-speed GTV CDN in universal 720p H.264/AAC MP4 format:
#   1. Sintel (2010) — Epic Fantasy / Dragon Quest (15 min)
#   2. Big Buck Bunny (2008) — Kids & Family Animated Comedy (10 min)
#   3. Tears of Steel (2012) — Live-Action + VFX Cyberpunk Sci-Fi (12 min)
#   4. Elephants Dream (2006) — Surreal Sci-Fi Short (11 min)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_ROOT="${1:-${SCRIPT_DIR}/media}"

mkdir -p "${MEDIA_ROOT}/movies"
mkdir -p "${MEDIA_ROOT}/kids-movies"

CDN="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample"

download_film() {
    local url="$1"
    local dest="$2"
    local tablet_dest="$3"
    local title="$4"

    if [[ -f "$dest" ]]; then
        echo "✓ Already downloaded: $title"
    else
        echo "==> Downloading $title..."
        curl -fL --progress-bar "$url" -o "$dest"
    fi

    # Create the '- Tablet 720p.mp4' hardlink so Fire Tablet offline drawer sees it immediately
    if [[ -n "$tablet_dest" && ! -f "$tablet_dest" ]]; then
        ln "$dest" "$tablet_dest" 2>/dev/null || cp "$dest" "$tablet_dest"
    fi
}

download_film \
    "${CDN}/Sintel.mp4" \
    "${MEDIA_ROOT}/movies/Sintel (2010) - 1080p.mp4" \
    "${MEDIA_ROOT}/movies/Sintel (2010) - Tablet 720p.mp4" \
    "Sintel (2010) [Fantasy / Dragon Quest]"

download_film \
    "${CDN}/BigBuckBunny.mp4" \
    "${MEDIA_ROOT}/kids-movies/Big Buck Bunny (2008) - 1080p.mp4" \
    "${MEDIA_ROOT}/kids-movies/Big Buck Bunny (2008) - Tablet 720p.mp4" \
    "Big Buck Bunny (2008) [Kids & Family Animation]"

download_film \
    "${CDN}/TearsOfSteel.mp4" \
    "${MEDIA_ROOT}/movies/Tears of Steel (2012) - 1080p.mp4" \
    "${MEDIA_ROOT}/movies/Tears of Steel (2012) - Tablet 720p.mp4" \
    "Tears of Steel (2012) [Cyberpunk Sci-Fi]"

download_film \
    "${CDN}/ElephantsDream.mp4" \
    "${MEDIA_ROOT}/movies/Elephants Dream (2006) - 1080p.mp4" \
    "${MEDIA_ROOT}/movies/Elephants Dream (2006) - Tablet 720p.mp4" \
    "Elephants Dream (2006) [Surreal Sci-Fi]"

echo "=============================================================================="
echo " ✅ 4 Free Open Movies downloaded to: ${MEDIA_ROOT}"
echo " Refresh http://localhost:8080 to stream or download them in Palantír!"
echo "=============================================================================="
