#!/usr/bin/env python3
"""
Syncs images from the Immich 'Documents' album to Paperless-ngx consume directory.
Runs periodically via systemd timer or cron.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths & Settings
CONTAINER_UPLOAD_PREFIX = "/usr/src/app/upload"
HOST_PHOTOS_ROOT = Path("/mnt/mithril/photos")
PAPERLESS_CONSUME_DIR = Path("/mnt/nvme/appdata/paperless/consume")
STATE_FILE = Path("/mnt/nvme/appdata/paperless/immich_synced_assets.json")
ALBUM_NAME = "Documents"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

def get_synced_ids() -> set:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return set(data.get("synced_asset_ids", []))
        except Exception as e:
            logging.warning(f"Failed to read state file: {e}")
    return set()

def save_synced_ids(synced_ids: set):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = STATE_FILE.with_suffix(".tmp")
    with open(temp_file, "w") as f:
        json.dump({"synced_asset_ids": sorted(list(synced_ids))}, f, indent=2)
    temp_file.replace(STATE_FILE)

def query_documents_assets() -> list:
    sql = f"""
    SELECT a.id, a."originalPath", a."originalFileName"
    FROM album_asset aa
    JOIN album al ON aa."albumId" = al.id
    JOIN asset a ON aa."assetId" = a.id
    WHERE al."albumName" = '{ALBUM_NAME}';
    """
    cmd = [
        "docker", "exec", "immich-postgres",
        "psql", "-U", "postgres", "-d", "immich",
        "-t", "-A", "-F", "|", "-c", sql
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to query Immich DB: {e.stderr}")
        return []

    assets = []
    for line in res.stdout.strip().splitlines():
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 3:
            assets.append({
                "id": parts[0].strip(),
                "originalPath": parts[1].strip(),
                "fileName": parts[2].strip()
            })
    return assets

def main():
    if not PAPERLESS_CONSUME_DIR.exists():
        logging.error(f"Consume directory {PAPERLESS_CONSUME_DIR} does not exist!")
        sys.exit(1)

    synced_ids = get_synced_ids()
    assets = query_documents_assets()
    logging.info(f"Found {len(assets)} assets in Immich '{ALBUM_NAME}' album. Already synced: {len(synced_ids)}.")

    new_synced = 0
    for item in assets:
        asset_id = item["id"]
        if asset_id in synced_ids:
            continue

        orig_path = item["originalPath"]
        if orig_path.startswith(CONTAINER_UPLOAD_PREFIX):
            rel_path = orig_path[len(CONTAINER_UPLOAD_PREFIX):].lstrip("/")
            src_file = HOST_PHOTOS_ROOT / rel_path
        else:
            src_file = Path(orig_path)

        if not src_file.exists():
            logging.warning(f"Source file not found on host: {src_file}")
            continue

        # Format filename to keep track of Immich asset ID
        ext = src_file.suffix
        clean_stem = Path(item["fileName"]).stem
        dest_filename = f"{clean_stem}_{asset_id[:8]}{ext}"
        dest_file = PAPERLESS_CONSUME_DIR / dest_filename

        try:
            shutil.copy2(src_file, dest_file)
            # Ensure paperless can read/delete the consumed file
            os.chmod(dest_file, 0o666)
            synced_ids.add(asset_id)
            new_synced += 1
            logging.info(f"Queued for Paperless: {dest_filename}")
        except Exception as e:
            logging.error(f"Failed to copy {src_file} -> {dest_file}: {e}")

    if new_synced > 0:
        save_synced_ids(synced_ids)
        logging.info(f"Successfully queued {new_synced} new document(s) for Paperless ingestion.")
    else:
        logging.info("Everything is up to date.")

if __name__ == "__main__":
    main()
