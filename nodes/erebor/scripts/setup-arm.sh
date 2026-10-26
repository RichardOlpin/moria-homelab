#!/usr/bin/env bash
# ==============================================================================
# Setup Automatic Ripping Machine (ARM) on 'erebor'
#
# Configures host optical drive detection, udev rules, QuickSync permissions,
# and ARM config so any inserted DVD/Blu-ray is auto-ripped and transcoded.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(cd "${SCRIPT_DIR}/../configs" && pwd)"

echo "==> Configuring Automatic Ripping Machine (ARM) on erebor..."

# 1. Install optical disc utilities
echo "==> Installing optical utilities (lsscsi, sg3-utils, eject)..."
apt-get update -qq
apt-get install -y -qq lsscsi sg3-utils eject

# 2. Ensure current user is in cdrom and render groups
TARGET_USER="${SUDO_USER:-$USER}"
echo "==> Granting optical & QuickSync permissions to user: ${TARGET_USER}..."
usermod -aG cdrom,render,video "${TARGET_USER}" || true

# 3. Create persistent directories
echo "==> Creating persistent ARM and media directories..."
mkdir -p /mnt/nvme/appdata/arm/config
mkdir -p /mnt/nvme/appdata/arm/logs
mkdir -p /mnt/mithril/media/movies
mkdir -p /mnt/mithril/media/tv
mkdir -p /mnt/mithril/media/music
mkdir -p /mnt/mithril/media/raw-rips

chown -R "${TARGET_USER}:${TARGET_USER}" /mnt/nvme/appdata/arm /mnt/mithril/media
chmod -R 775 /mnt/nvme/appdata/arm /mnt/mithril/media

# 4. Deploy tuned arm.yaml configuration
if [[ -f "${CONFIG_DIR}/arm.yaml" ]]; then
    echo "==> Deploying tuned arm.yaml to /mnt/nvme/appdata/arm/config/arm.yaml..."
    cp "${CONFIG_DIR}/arm.yaml" /mnt/nvme/appdata/arm/config/arm.yaml
    chown "${TARGET_USER}:${TARGET_USER}" /mnt/nvme/appdata/arm/config/arm.yaml
fi

# 5. Create udev trigger helper script
echo "==> Creating /usr/local/bin/arm-udev-trigger.sh..."
cat << 'EOF' > /usr/local/bin/arm-udev-trigger.sh
#!/usr/bin/env bash
DEVNAME="$1"
LOGFILE="/var/log/arm-udev.log"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

echo "[$TS] Optical disc insertion detected on /dev/${DEVNAME}" >> "$LOGFILE"

# Wait briefly for drive spinup
sleep 4

# If the ARM docker container is running, trigger arm_wrapper.sh
if docker ps --format '{{.Names}}' | grep -q '^arm-ripper$'; then
    echo "[$TS] Triggering arm_wrapper.sh inside arm-ripper container for /dev/${DEVNAME}..." >> "$LOGFILE"
    docker exec -d arm-ripper /opt/arm/scripts/arm_wrapper.sh "$DEVNAME"
else
    echo "[$TS] WARNING: arm-ripper container is not currently running. Run 'docker compose up -d arm-ripper' in /opt/stacks/erebor." >> "$LOGFILE"
fi
EOF
chmod +x /usr/local/bin/arm-udev-trigger.sh

# 6. Deploy udev rule and reload
echo "==> Installing udev rule to /etc/udev/rules.d/51-arm.rules..."
cp "${CONFIG_DIR}/51-arm.rules" /etc/udev/rules.d/51-arm.rules
udevadm control --reload-rules
udevadm trigger

echo ""
echo "=============================================================================="
echo " ✅ Automatic Ripping Machine (ARM) Host Setup Complete!"
echo " Insert any commercial DVD, Blu-ray, or CD into the USB optical drive."
echo " The disc will auto-rip, hardware-transcode via QuickSync, and auto-eject!"
echo " Monitor live rips at: https://rip.moria.lan or http://erebor.moria.lan:8088"
echo "=============================================================================="
