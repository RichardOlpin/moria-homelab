#!/usr/bin/env bash
# ==============================================================================
# Bootstrap Script for Node 1: gandalf (2015 Lenovo Yoga 900)
# OS: Ubuntu Server 24.04 LTS (Headless)
# Role: Perimeter Gatekeeper, DNS, Reverse Proxy, Auth, Vaultwarden, GitOps
# ==============================================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "Please run as root: sudo ./bootstrap-ubuntu.sh"
   exit 1
fi

echo "==> [1/6] Setting hostname to 'gandalf'..."
hostnamectl set-hostname gandalf

echo "==> [2/6] Installing essential packages & utilities..."
apt-get update -y
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban \
    wakeonlan \
    ethtool \
    btop \
    htop \
    tmux \
    unzip \
    lm-sensors \
    acpi

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
    usermod -aG docker "$SUDO_USER"
    echo "    Added user '$SUDO_USER' to the docker group."
fi

echo "==> [4/6] Configuring Lenovo Yoga 900 Lid-Close Ignore & Console Blank..."
# Prevent closing the laptop lid from suspending the server
sed -i 's/^#*HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sed -i 's/^#*HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
sed -i 's/^#*HandleLidSwitchDocked=.*/HandleLidSwitchDocked=ignore/' /etc/systemd/logind.conf
systemctl restart systemd-logind

echo "==> [5/6] Enabling Lenovo Battery Conservation Mode (~60% Charge Cap UPS)..."
# Lenovo Yoga 900 uses ideapad_acpi conservation_mode to prevent battery swelling while plugged in 24/7
cat << 'EOF' > /etc/systemd/system/lenovo-battery-conservation.service
[Unit]
Description=Enable Lenovo IdeaPad/Yoga Battery Conservation Mode (60% UPS Cap)
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'for f in /sys/bus/platform/drivers/ideapad_acpi/*/conservation_mode; do [ -e "$f" ] && echo 1 > "$f"; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now lenovo-battery-conservation.service || true

echo "==> [6/6] Freeing Port 53 for Pi-hole (disabling systemd-resolved stub)..."
mkdir -p /etc/systemd/resolved.conf.d
cat << 'EOF' > /etc/systemd/resolved.conf.d/pihole.conf
[Resolve]
DNS=127.0.0.1
DNSStubListener=no
EOF
ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
systemctl reload-or-restart systemd-resolved

echo "==> Creating stack directories under /opt/gandalf..."
mkdir -p /opt/gandalf/{caddy,pihole/etc-pihole,pihole/etc-dnsmasq.d,vaultwarden,forgejo,pocketid,upsnap}

# Pre-seed split-horizon DNS for *.moria.lan in Pi-hole dnsmasq config if not present
if [ ! -f /opt/gandalf/pihole/etc-dnsmasq.d/02-moria-lan.conf ]; then
    cat << 'EOF' > /opt/gandalf/pihole/etc-dnsmasq.d/02-moria-lan.conf
# Split-Horizon DNS: Route *.moria.lan to gandalf reverse proxy
address=/moria.lan/192.168.1.10
EOF
fi

if [[ -n "${SUDO_USER:-}" ]]; then
    chown -R "$SUDO_USER:$SUDO_USER" /opt/gandalf
fi

echo "=============================================================================="
echo " 'Speak, friend, and enter.' — gandalf bootstrap complete!"
echo " Next steps:"
echo "   1. Copy compose.yaml, Caddyfile, and .env.example (as .env) to /opt/gandalf"
echo "   2. Run: cd /opt/gandalf && docker compose up -d"
echo "=============================================================================="
