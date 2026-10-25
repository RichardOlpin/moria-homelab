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
    usermod -aG docker,render,video "$SUDO_USER"
    echo "    Added '$SUDO_USER' to docker, render, and video groups (for Intel QuickSync /dev/dri)."
fi

echo "==> [4/6] Tuning ZFS ARC Memory Cap (Max 16GB of 32GB RAM so Docker/AI has 16GB free)..."
echo "options zfs zfs_arc_max=17179869184" > /etc/modprobe.d/zfs.conf

echo "==> [5/7] Preparing fast NVMe directories for Docker & AI Workspaces..."
mkdir -p /mnt/nvme/{appdata,workspaces,stacks}
mkdir -p /mnt/nvme/appdata/{jellyfin,immich-pg,immich-cache,radarr,sonarr,prowlarr,bazarr,jellyseerr,code-server}
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

echo "==> [7/7] Printing ZFS 'mithril' Pool Creation Template..."
cat << 'EOF'
==============================================================================
 'erebor' Bootstrap Complete!
==============================================================================
When your 3x 14TB drives are installed, verify their IDs with:
  ls -l /dev/disk/by-id/ | grep -v part

Then create your 28TB usable 'mithril' ZFS RAIDZ1 pool using:

  sudo zpool create -f \
    -o ashift=12 \
    -o autotrim=on \
    -O acltype=posixacl \
    -O xattr=sa \
    -O dnodesize=auto \
    -O compression=lz4 \
    -O normalization=formD \
    -O relatime=on \
    -m /mnt/mithril \
    mithril raidz1 \
    /dev/disk/by-id/ata-DRIVE_1 \
    /dev/disk/by-id/ata-DRIVE_2 \
    /dev/disk/by-id/ata-DRIVE_3

Create optimized datasets for Media, Photos, Cloud, and M1 MacBook Time Machine:

  # 1M recordsize for large sequential video streaming (Palantir / Jellyfin)
  sudo zfs create -o recordsize=1M mithril/media
  sudo mkdir -p /mnt/mithril/media/{movies,tv,kids-movies,kids-tv,downloads}

  # 128K recordsize for Immich raw photo library & Nextcloud/Seafile
  sudo zfs create -o recordsize=128K mithril/photos
  sudo zfs create -o recordsize=128K mithril/cloud

  # Quota-capped 1.5TB dataset for M1 MacBook Pro ('strider') Time Machine backups
  sudo zfs create -o recordsize=1M -o compression=zstd -o quota=1500G mithril/timemachine

  # Nightly backup target for NVMe appdata & gandalf configs
  sudo zfs create -o compression=zstd mithril/backups
==============================================================================
EOF
