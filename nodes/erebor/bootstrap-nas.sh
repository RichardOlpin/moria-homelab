#!/usr/bin/env bash
# ==============================================================================
# Bootstrap Script for Node 2: erebor (Custom i3-12100 28TB ZFS NAS & AI Server)
# OS: Ubuntu Server 24.04 LTS (Headless)
# Role: 'mithril' ZFS Storage Pool, Intel QuickSync Media Engine, AI App Factory
# ==============================================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "Please run as root: sudo ./bootstrap-nas.sh"
   exit 1
fi

echo "==> [1/6] Setting hostname to 'erebor'..."
hostnamectl set-hostname erebor

echo "==> [2/6] Installing OpenZFS, Samba (Mac Time Machine), Intel QuickSync & UPS tools..."
apt-get update -y
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    git \
    zfsutils-linux \
    sanoid \
    samba \
    nfs-kernel-server \
    smartmontools \
    intel-gpu-tools \
    vainfo \
    nut \
    btop \
    htop \
    tmux \
    iotop \
    ncdu

echo "==> [3/6] Installing official Docker Engine & Compose plugin..."
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

if [[ -n "${SUDO_USER:-}" ]]; then
    usermod -aG docker,render,video,cdrom "$SUDO_USER"
    echo "    Added '$SUDO_USER' to docker, render, video, and cdrom groups (for QuickSync /dev/dri & USB DVD /dev/sr0)."
fi

echo "==> [4/7] Tuning ZFS ARC Memory Cap (50% of total RAM so Docker/AI always has 50% free)..."
TOTAL_MEM_BYTES=$(awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo)
ARC_MAX_BYTES=$(( TOTAL_MEM_BYTES / 2 ))
echo "options zfs zfs_arc_max=${ARC_MAX_BYTES}" > /etc/modprobe.d/zfs.conf
echo "    Set zfs_arc_max=${ARC_MAX_BYTES} bytes (~$(( ARC_MAX_BYTES / 1024 / 1024 / 1024 ))GB)."

echo "==> [5/7] Preparing fast NVMe directories for Docker, DVD Ripper & AI Workspaces..."
mkdir -p /mnt/nvme/{appdata,workspaces,stacks}
mkdir -p /mnt/nvme/appdata/{jellyfin,immich-pg,immich-cache,radarr,sonarr,prowlarr,bazarr,jellyseerr,code-server,romm/resources,romm/redis-data,romm-db,arm/config}
cp "${BASH_SOURCE[0]%/*}/configs/arm.yaml" /mnt/nvme/appdata/arm/config/arm.yaml
if [[ -n "${SUDO_USER:-}" ]]; then
    chown -R "$SUDO_USER:$SUDO_USER" /mnt/nvme
fi

echo "==> [6/7] Installing Sanoid ZFS snapshot policy, Samba Time Machine config & Nightly Backup Cron..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /etc/sanoid
cp "${SCRIPT_DIR}/configs/sanoid.conf" /etc/sanoid/sanoid.conf
systemctl enable --now sanoid.timer || true

cp "${SCRIPT_DIR}/configs/smb.conf" /etc/samba/smb.conf
systemctl restart smbd || true

install -m 0755 "${SCRIPT_DIR}/scripts/nightly-backup.sh" /usr/local/sbin/moria-nightly-backup
cat << 'EOF' > /etc/cron.d/moria-backup
# Run Moria Nightly Backup at 03:00 AM daily
0 3 * * * root /usr/local/sbin/moria-nightly-backup >> /var/log/moria-backup.log 2>&1
EOF

echo "==> Configuring Automatic Ripping Machine (ARM) host udev & permissions..."
if [[ -f "${SCRIPT_DIR}/scripts/setup-arm.sh" ]]; then
    bash "${SCRIPT_DIR}/scripts/setup-arm.sh"
fi

echo "==> [7/7] Printing ZFS 'mithril' Pool Creation Template..."
cat << 'EOF'
==============================================================================
 'erebor' Bootstrap Complete!
==============================================================================
Verify your installed hard drive IDs with:
  ls -l /dev/disk/by-id/ | grep -v part

OPTION A1 — Single-Drive Start (1x 10TB Enterprise SATA Drive, expandable to Mirror later):
  sudo zpool create -f \
    -o ashift=12 -o autotrim=on \
    -O acltype=posixacl -O xattr=sa -O dnodesize=auto \
    -O compression=lz4 -O normalization=formD -O relatime=on \
    -m /mnt/mithril mithril \
    /dev/disk/by-id/ata-DRIVE_1
  # Later, convert live to a redundant 2-drive ZFS Mirror without losing data:
  # sudo zpool attach mithril /dev/disk/by-id/ata-DRIVE_1 /dev/disk/by-id/ata-DRIVE_2

OPTION A2 — Recommended Redundant Start (2x 10TB Enterprise ZFS Mirror = ~9.1 TiB usable):
  sudo zpool create -f \
    -o ashift=12 -o autotrim=on \
    -O acltype=posixacl -O xattr=sa -O dnodesize=auto \
    -O compression=lz4 -O normalization=formD -O relatime=on \
    -m /mnt/mithril mithril mirror \
    /dev/disk/by-id/ata-DRIVE_1 \
    /dev/disk/by-id/ata-DRIVE_2

OPTION B — 3-Drive Build (3x 10TB ZFS RAIDZ1 = ~18.2 TiB usable):
  sudo zpool create -f \
    -o ashift=12 -o autotrim=on \
    -O acltype=posixacl -O xattr=sa -O dnodesize=auto \
    -O compression=lz4 -O normalization=formD -O relatime=on \
    -m /mnt/mithril mithril raidz1 \
    /dev/disk/by-id/ata-DRIVE_1 \
    /dev/disk/by-id/ata-DRIVE_2 \
    /dev/disk/by-id/ata-DRIVE_3

Create optimized datasets for Media, Photos, Cloud, ROMs, and M1 MacBook Time Machine:

  # 1M recordsize for large sequential video streaming (Palantir / Jellyfin) & Retro ROMs (RomM)
  sudo zfs create -o recordsize=1M mithril/media
  sudo mkdir -p /mnt/mithril/media/{movies,tv,kids-movies,kids-tv,downloads}
  sudo zfs create -o recordsize=1M mithril/roms
  sudo mkdir -p /mnt/mithril/roms/{library,assets,config}

  # 128K recordsize for Immich raw photo library & Papra Document Vault
  sudo zfs create -o recordsize=128K mithril/photos
  sudo zfs create -o recordsize=128K mithril/cloud
  sudo mkdir -p /mnt/mithril/cloud/papra

  # Quota-capped 1.5TB dataset for M1 MacBook Pro ('strider') Time Machine backups
  sudo zfs create -o recordsize=1M -o compression=zstd -o quota=1500G mithril/timemachine

  # Nightly backup target for NVMe appdata & gandalf configs
  sudo zfs create -o compression=zstd mithril/backups
==============================================================================
EOF
