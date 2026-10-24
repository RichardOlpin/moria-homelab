# Moria Homelab (`*.moria.lan`)

> *"Speak, friend, and enter."*

Declarative infrastructure, Ubuntu 24.04 LTS bootstrap scripts, and Docker Compose stacks for the **Moria** homelab behind the `SpeakFriend&Enter` network.

## Node Map & Hardware Topology

| Hostname | Hardware | OS | Role & Workloads |
| :--- | :--- | :--- | :--- |
| **`gandalf`** | 2015 Lenovo Yoga 900 (i7-6500U, 16GB RAM, 512GB SSD, built-in 60%-capped battery UPS) | Ubuntu Server 24.04 LTS | **Perimeter Gatekeeper & Always-On Infra**: Caddy + CrowdSec, AdGuard Home (`*.moria.lan` DNS), PocketID Passkey SSO, Vaultwarden, Forgejo Git, UpSnap (Wake-on-LAN). |
| **`erebor`** | Custom mATX NAS (Intel i3-12100 UHD 730 QuickSync, 32GB RAM, 1TB NVMe, **3x 14TB ZFS RAIDZ1 `mithril` = 28TB usable**) | Ubuntu Server 24.04 LTS + OpenZFS | **Storage Core & AI App Factory**: ZFS pool `mithril`, `Palantir` (Jellyfin QuickSync engine + custom AI UI), Immich, `*arr` suite, Mac Time Machine SMB target, 24/7 AI coding containers. |
| **`balrog`** | Gaming PC (AMD 9800X3D, Nvidia RTX 5070, 1TB SSD) | Windows / WSL2 or Dual-Boot | **On-Demand GPU Beast (Wake-on-LAN)**: Woken automatically by `gandalf` for Immich ML facial/CLIP indexing, Whisper subtitle generation, `pgvector` embeddings, and AV1 batch encoding. |
| **`strider`** | M1 MacBook Pro (32GB Unified Memory, 1TB SSD) | macOS | **Command Workstation & High-VRAM Local LLM Host**: Connects to `erebor` & `gandalf` over Remote-SSH, backs up automatically via Time Machine to `mithril/timemachine`, and can run 27B–32B parameter local models in 32GB Unified Memory. |

## Repository Structure

* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Full $1,000 hardware bill of materials, network topology diagrams, ZFS pool layout, and phased rollout blueprint.
* [`nodes/gandalf/bootstrap-ubuntu.sh`](nodes/gandalf/bootstrap-ubuntu.sh) — Configures Ubuntu 24.04 on the Lenovo Yoga 900 (Docker, lid-close ignore, 60% Lenovo battery conservation UPS mode, port 53 DNS prep).
* [`nodes/gandalf/compose.yaml`](nodes/gandalf/compose.yaml) & [`nodes/gandalf/Caddyfile`](nodes/gandalf/Caddyfile) — Reverse proxy, split-horizon DNS, Passkey SSO, Vaultwarden, Forgejo, and Wake-on-LAN controller.
* [`nodes/erebor/bootstrap-nas.sh`](nodes/erebor/bootstrap-nas.sh) — Configures Ubuntu 24.04 + OpenZFS (`mithril` RAIDZ1 pool), Intel QuickSync (`/dev/dri`), ZFS ARC tuning, and Time Machine dataset for the M1 MacBook Pro.
* [`nodes/erebor/compose.yaml`](nodes/erebor/compose.yaml) — Jellyfin hardware-transcoding engine for **Palantir**, Immich photo cloud, `*arr` stack, and the 24/7 AI Coding Workbench.
* [`nodes/erebor/scripts/optimize-for-tablet.sh`](nodes/erebor/scripts/optimize-for-tablet.sh) — Hardware-accelerated Intel QuickSync script to generate fast-downloading `Tablet 720p.mp4` files for Amazon Fire Tablets.
* [`macbook-strider/ssh_config.example`](macbook-strider/ssh_config.example) — Drop-in `~/.ssh/config` for the M1 MacBook Pro (including SSH Agent Forwarding and automatic Wake-on-LAN on `ssh balrog`).
* [`.githooks/pre-push`](.githooks/pre-push) — Local Git hook that blocks direct pushes to `main` so all changes are grouped and documented via Pull Requests.

## Quickstart (SSH Only)

Because `ForwardAgent yes` is enabled in [`macbook-strider/ssh_config.example`](macbook-strider/ssh_config.example), when you SSH from **`strider`** (M1 MacBook Pro) into **`gandalf`** or **`erebor`**, your GitHub SSH key is forwarded automatically—no need to copy private keys onto the servers:

```bash
# On gandalf (Lenovo Yoga 900):
git clone git@github.com:RichardOlpin/moria-homelab.git
cd moria-homelab
git config core.hooksPath .githooks
cd nodes/gandalf
sudo ./bootstrap-ubuntu.sh
```

## Git & Pull Request Workflow

Direct pushes to `main` are blocked by [`.githooks/pre-push`](.githooks/pre-push). All updates go through feature branches and Pull Requests for clean historical context:

```bash
# Enable the repo-tracked pre-push hook once after cloning:
git config core.hooksPath .githooks

# Create a feature branch, commit, and push over SSH:
git checkout -b feat/describe-change
git add .
git commit -m "Describe change"
git push -u origin feat/describe-change
```
