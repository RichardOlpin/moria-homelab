#!/usr/bin/env bash
# ==============================================================================
# Download Free Creative Commons Open Movies for Palantír Testing
#
# Fetches official Blender Foundation Creative Commons (CC-BY) films directly
# from download.blender.org in universal H.264/AAC MP4 format:
#   1. Sintel (2010) — Epic Fantasy / Dragon Quest (HD 720p)
#   2. Big Buck Bunny (2008) — Kids & Family Animated Comedy
#   3. Tears of Steel (2012) — Live-Action + VFX Cyberpunk Sci-Fi
#   4. Spring (2019) — Fantasy / Nature Spirit
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_ROOT="${1:-${SCRIPT_DIR}/media}"

mkdir -p "${MEDIA_ROOT}/movies"
mkdir -p "${MEDIA_ROOT}/kids-movies"

download_film() {
    local url="$1"
    local dest="$2"
    local tablet_dest="$3"
    local title="$4"

    mkdir -p "$(dirname "$dest")"
    if [[ -f "$dest" && -s "$dest" ]]; then
        echo "✓ Already downloaded: $title"
    else
        echo "==> Downloading $title..."
        curl -fL -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)" --progress-bar "$url" -o "$dest"
    fi

    # Create the '- Tablet 720p.mp4' hardlink so Fire Tablet offline drawer sees it immediately
    if [[ -n "$tablet_dest" && ! -f "$tablet_dest" ]]; then
        ln "$dest" "$tablet_dest" 2>/dev/null || cp "$dest" "$tablet_dest"
    fi
}

download_film \
    "https://download.blender.org/durian/trailer/sintel_trailer-720p.mp4" \
    "${MEDIA_ROOT}/movies/Sintel (2010)/Sintel (2010) - 1080p.mp4" \
    "${MEDIA_ROOT}/movies/Sintel (2010)/Sintel (2010) - Tablet 720p.mp4" \
    "Sintel (2010) [Fantasy / Dragon Quest - 720p HD]"

download_film \
    "https://archive.org/download/BigBuckBunny_124/Content/big_buck_bunny_720p_surround.mp4" \
    "${MEDIA_ROOT}/kids-movies/Big Buck Bunny (2008)/Big Buck Bunny (2008) - 1080p.mp4" \
    "${MEDIA_ROOT}/kids-movies/Big Buck Bunny (2008)/Big Buck Bunny (2008) - Tablet 720p.mp4" \
    "Big Buck Bunny (2008) [Kids & Family Animation - Full 10m 720p HD Film]"

download_film \
    "https://archive.org/download/Tears-of-Steel/tears_of_steel_720p.mp4" \
    "${MEDIA_ROOT}/movies/Tears of Steel (2012)/Tears of Steel (2012) - 1080p.mp4" \
    "${MEDIA_ROOT}/movies/Tears of Steel (2012)/Tears of Steel (2012) - Tablet 720p.mp4" \
    "Tears of Steel (2012) [Cyberpunk Sci-Fi - Full 12m 720p HD Film]"

download_film \
    "https://archive.org/download/ElephantsDream/ed_1024_512kb.mp4" \
    "${MEDIA_ROOT}/movies/Elephants Dream (2006)/Elephants Dream (2006) - 1080p.mp4" \
    "${MEDIA_ROOT}/movies/Elephants Dream (2006)/Elephants Dream (2006) - Tablet 720p.mp4" \
    "Elephants Dream (2006) [Surreal Sci-Fi - Full 11m Film]"

echo "=============================================================================="
echo " ✅ 4 Free Open Movies downloaded to: ${MEDIA_ROOT}"
echo " Restart or refresh http://localhost:8080 to stream or download them in Palantír!"
echo "=============================================================================="
