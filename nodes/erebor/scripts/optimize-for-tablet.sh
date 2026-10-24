#!/usr/bin/env bash
# ==============================================================================
# Palantir Fire Tablet Optimizer (Intel QuickSync h264_qsv)
# Runs on 'erebor' to pre-generate ultra-compatible, fast-downloading
# "- Tablet 720p.mp4" versions alongside 4K/1080p media files.
#
# Jellyfin automatically merges files named:
#   Movie (Year) - 1080p.mkv
#   Movie (Year) - Tablet 720p.mp4
# into a single library item, allowing Fire Tablets to download a full movie
# over Wi-Fi in ~15 seconds without waiting for live transcoding.
# ==============================================================================
set -euo pipefail

TARGET_DIR="${1:-/mnt/mithril/media/kids-movies}"

if [[ ! -d "$TARGET_DIR" ]]; then
    echo "Usage: $0 [/path/to/media/folder]"
    exit 1
fi

echo "==> Scanning '$TARGET_DIR' for videos missing a '- Tablet 720p.mp4' version..."

find "$TARGET_DIR" -type f \( -name "*.mkv" -o -name "*.mp4" \) ! -name "*- Tablet 720p.mp4" | while read -r src_file; do
    dir_name="$(dirname "$src_file")"
    base_name="$(basename "$src_file")"
    stem="${base_name%.*}"
    # Strip existing resolution suffix if present (e.g., " - 1080p" or " - 4K")
    clean_stem="$(echo "$stem" | sed -E 's/ - (2160p|4K|1080p|Bluray|Remux).*//I')"
    out_file="${dir_name}/${clean_stem} - Tablet 720p.mp4"

    if [[ -f "$out_file" ]]; then
        continue
    fi

    echo "==> [QuickSync QSV] Generating Fire Tablet 720p MP4 for: $base_name"
    docker run --rm \
        --device /dev/dri:/dev/dri \
        -v "$dir_name:/work" \
        jellyfin/jellyfin-ffmpeg:latest \
        ffmpeg -y -hide_banner -loglevel warning -stats \
        -hwaccel qsv -hwaccel_output_format qsv \
        -i "/work/$base_name" \
        -vf "scale_qsv=w=1280:h=-1:format=nv12" \
        -c:v h264_qsv -preset medium -global_quality 23 -maxrate 3500k -bufsize 7000k \
        -c:a aac -ac 2 -b:a 160k \
        -movflags +faststart \
        "/work/$(basename "$out_file")"

    echo "    Created: $out_file"
done

echo "==> All media in '$TARGET_DIR' is Fire Tablet ready!"
