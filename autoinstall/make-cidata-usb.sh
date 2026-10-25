#!/usr/bin/env bash
# ==============================================================================
# macOS ('strider') Helper: Create a Cloud-Init 'CIDATA' Seed USB for Autoinstall
#
# Ubuntu 24.04 Live Server automatically detects any FAT32 volume labeled
# 'CIDATA' containing `user-data` and `meta-data` at boot and performs a 100%
# unattended installation (importing ssh-import-id gh:RichardOlpin).
#
# Usage on macOS:
#   ./autoinstall/make-cidata-usb.sh <gandalf|erebor> /dev/diskN
# ==============================================================================
set -euo pipefail

NODE="${1:-}"
DISK_DEV="${2:-}"

if [[ "$NODE" != "gandalf" && "$NODE" != "erebor" ]] || [[ -z "$DISK_DEV" ]]; then
    echo "Usage: $0 <gandalf|erebor> /dev/diskN"
    echo ""
    echo "Available external disks on macOS:"
    diskutil list external
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${SCRIPT_DIR}/${NODE}"

echo "⚠️  WARNING: This will erase '${DISK_DEV}' and format it as FAT32 volume 'CIDATA' for node '${NODE}'."
read -r -p "Type 'mellon' to continue: " confirm
if [[ "$confirm" != "mellon" ]]; then
    echo "Aborted."
    exit 1
fi

echo "==> Formatting ${DISK_DEV} as FAT32 with label CIDATA..."
diskutil eraseDisk FAT32 CIDATA MBRFormat "$DISK_DEV"

echo "==> Copying ${NODE} user-data and meta-data to /Volumes/CIDATA..."
cp "${SRC_DIR}/user-data" /Volumes/CIDATA/user-data
cp "${SRC_DIR}/meta-data" /Volumes/CIDATA/meta-data
sync

echo "==> Ejecting ${DISK_DEV}..."
diskutil eject "$DISK_DEV"

echo "=============================================================================="
echo " ✅ CIDATA seed USB ready for '${NODE}'!"
echo " Plug both your Ubuntu 24.04 Live Server USB and this CIDATA USB into ${NODE}"
echo " and boot from the Ubuntu USB. It will install unattended and power off when done."
echo "=============================================================================="
