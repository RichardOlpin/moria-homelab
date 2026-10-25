#!/usr/bin/env bash
# ==============================================================================
# Nightly Homelab Backup Script (Runs on 'erebor' at 03:00 AM via cron)
# Protects single-disk NVMe appdata/DBs and 'gandalf' configs onto the
# redundant 3-disk ZFS RAIDZ1 dataset: /mnt/mithril/backups
# ==============================================================================
set -euo pipefail

BACKUP_ROOT="/mnt/mithril/backups"
GANDALF_HOST="${GANDALF_HOST:-ubuntu@gandalf.moria.lan}"
DATE_TAG="$(date +%Y-%m-%d_%H%M)"

if [[ ! -d "$BACKUP_ROOT" ]]; then
    echo "ERROR: $BACKUP_ROOT does not exist (is ZFS pool 'mithril' mounted?)" >&2
    exit 1
fi

mkdir -p "${BACKUP_ROOT}/erebor-nvme/db-dumps"
mkdir -p "${BACKUP_ROOT}/erebor-nvme/appdata"
mkdir -p "${BACKUP_ROOT}/erebor-nvme/workspaces"
mkdir -p "${BACKUP_ROOT}/gandalf"

echo "==> [1/4] Dumping Immich Postgres database cleanly..."
if docker ps --format '{{.Names}}' | grep -q '^immich-postgres$'; then
    docker exec immich-postgres pg_dumpall -U postgres | gzip > "${BACKUP_ROOT}/erebor-nvme/db-dumps/immich-pg-${DATE_TAG}.sql.gz"
    # Keep last 14 daily SQL dumps
    find "${BACKUP_ROOT}/erebor-nvme/db-dumps" -type f -name "*.sql.gz" -mtime +14 -delete
fi

echo "==> [2/4] Syncing erebor NVMe appdata & AI workspaces to ZFS RAIDZ1..."
rsync -a --delete \
    --exclude 'immich-cache/' \
    --exclude 'jellyfin/cache/' \
    /mnt/nvme/appdata/ "${BACKUP_ROOT}/erebor-nvme/appdata/"

rsync -a --delete \
    --exclude 'node_modules/' \
    --exclude '.next/' \
    --exclude 'target/' \
    /mnt/nvme/workspaces/ "${BACKUP_ROOT}/erebor-nvme/workspaces/"

echo "==> [3/4] Pulling gandalf (/opt/gandalf) configs & Vaultwarden DB over SSH..."
if ssh -o BatchMode=yes -o ConnectTimeout=5 "$GANDALF_HOST" "true" 2>/dev/null; then
    rsync -az --delete "${GANDALF_HOST}:/opt/gandalf/" "${BACKUP_ROOT}/gandalf/"
else
    echo "    WARN: Could not reach $GANDALF_HOST over SSH; skipping remote pull."
fi

echo "==> [4/4] Creating atomic ZFS snapshot mithril/backups@nightly-${DATE_TAG}..."
if command -v zfs &>/dev/null; then
    zfs snapshot "mithril/backups@nightly-${DATE_TAG}" || true
fi

echo "==> Nightly Moria backup completed at $(date)!"
