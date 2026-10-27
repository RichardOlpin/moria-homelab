# Moria Homelab (`moria-homelab`) Agent Rules

## 1. Git, SSH & Pull Request Workflow
* **SSH Only**: Always use SSH (`git@github.com:RichardOlpin/moria-homelab.git`) for all Git remotes and clone instructions. Never use HTTPS Git URLs.
* **No Direct Pushes to `main`**: Direct pushes to `main` are blocked by `.githooks/pre-push`.
* **PR-Per-Chunk Workflow**: Group every logical chunk of changes onto its own feature branch (`feat/<name>`, `fix/<name>`, or `chore/<name>`), push the branch to `origin`, create a Pull Request with a clear historical summary of what was added, and merge the PR (`gh pr merge <num> --merge --delete-branch`).

## 2. Prefix-Matchable Command Shapes (`git push *` Auto-Approval)
* **Never chain `git` or `gh` commands with `&&`, `;`, `||`, or command substitutions (`$(...)` / backticks)**.
* Always execute `git checkout`, `git add`, `git commit`, `git push`, `/opt/homebrew/bin/gh pr create`, and `/opt/homebrew/bin/gh pr merge` as **single standalone commands** with single-quoted strings (`'...'`). This ensures the user's prefix-based **"Always allow `git push`"** (and related `git` / `gh` approvals) match automatically without re-prompting.

## 3. Homelab Node Topology (`*.moria.lan`)
* **`gandalf`** — 2015 Lenovo Yoga 900 (Ubuntu Server 24.04 LTS, 60% battery conservation UPS mode, Caddy, Pi-hole, PocketID, Vaultwarden, Forgejo, UpSnap Wake-on-LAN).
* **`erebor`** — Custom Intel i3-12100 mATX NAS (Ubuntu Server 24.04 LTS, 32GB RAM, 1TB NVMe, 3x 14TB ZFS RAIDZ1 pool `mithril`, `Palantír` + Jellyfin QuickSync engine, Immich, `*arr` suite, RomM, Papra, AI Coding Workbench).
* **`balrog`** — Gaming PC (AMD 7800X3D + Nvidia RTX 5070, woken on-demand via Wake-on-LAN for CUDA Immich ML, Ollama, and Faster-Whisper subtitles, with 20-minute idle auto-sleep).
* **`strider`** — M1 MacBook Pro (32GB Unified Memory workstation, wireless Time Machine backups to `mithril/timemachine`, Remote-SSH client).
