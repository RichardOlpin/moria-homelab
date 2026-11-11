#!/usr/bin/env bash

# -------------------------------------------------------------------
# setup_erebor_ssh.sh
#
# This script is intended to be run **on erebor** (the NAS node) after
# you have pulled the `moria-homelab` repository onto the machine.
# It performs the full, automated workflow to:
#   1. Generate an ED25519 SSH key (no pass‑phrase).
#   2. Upload the public key to GitHub via the API (requires a PAT).
#   3. Install the public key into the local `authorized_keys` so that
#      the user can SSH from any other trusted host (e.g., Gandalf).
#   4. Test the SSH connection to GitHub.
#   5. Optionally switch the repo’s remote from HTTPS to SSH.
#
# Prerequisites on erebor:
#   * `ssh-keygen`, `curl`, `jq`, `git` must be installed.
#   * You must have a GitHub Personal Access Token (PAT) with the
#     `admin:public_key` scope. The token can be supplied via the
#     environment variable GITHUB_PAT, or the script will prompt for it.
#
# Usage:
#   chmod +x scripts/setup_erebor_ssh.sh
#   ./scripts/setup_erebor_ssh.sh    # run as the user that will own the key
#
# -------------------------------------------------------------------

set -euo pipefail

# -------------------- Configurable variables --------------------
# Name of the key file (will be placed in ~/.ssh/)
KEY_NAME="id_ed25519_erebor"
# Comment that will appear in the public key
KEY_COMMENT="$(whoami)@erebor.moria.lan"
# Path to the key (expanded later)
SSH_DIR="$HOME/.ssh"
KEY_PATH="$SSH_DIR/$KEY_NAME"
# GitHub repository (used for switching remote if desired)
REPO_SSH_URL="git@github.com:RichardOlpin/moria-homelab.git"
# ----------------------------------------------------------------

# Helper: print a nice header
log() {
    echo -e "\n=== $* ==="
}

# 1️⃣ Ensure required tools are present
log "Checking required tools"
for cmd in ssh-keygen curl jq git; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Error: $cmd is not installed. Install it and re‑run the script." >&2
        exit 1
    fi
done

# 2️⃣ Create ~/.ssh if needed and set permissions
log "Ensuring $SSH_DIR exists with correct permissions"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

# 3️⃣ Generate the ED25519 key if it does not already exist
if [[ -f "$KEY_PATH" ]]; then
    log "Key $KEY_PATH already exists – leaving it unchanged"
else
    log "Generating ED25519 key $KEY_PATH"
    ssh-keygen -t ed25519 -a 100 -C "$KEY_COMMENT" -f "$KEY_PATH" -N ""
    chmod 600 "$KEY_PATH"
fi

# 4️⃣ Read the public key
PUB_KEY=$(cat "${KEY_PATH}.pub")

# 5️⃣ Obtain GitHub PAT (from env or prompt)
if [[ -z "${GITHUB_PAT:-}" ]]; then
    read -rsp "Enter your GitHub Personal Access Token (admin:public_key scope): " GITHUB_PAT
    echo
fi

# 6️⃣ Upload the public key to GitHub via API
log "Uploading public key to GitHub"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
GITHUB_LABEL="erebor-ed25519-${TIMESTAMP}"
API_RESPONSE=$(curl -s -X POST \
    -H "Authorization: token $GITHUB_PAT" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/user/keys \
    -d "{\"title\": \"$GITHUB_LABEL\", \"key\": \"$PUB_KEY\"}")

if echo "$API_RESPONSE" | grep -q '"id":'; then
    echo "✅ SSH key added to GitHub successfully."
    echo "$API_RESPONSE" | jq .
else
    echo "❌ Failed to add key to GitHub. Response:" >&2
    echo "$API_RESPONSE" >&2
    exit 1
fi

# 7️⃣ Add the public key to local authorized_keys (for Gandalf etc.)
log "Adding public key to $HOME/.ssh/authorized_keys"
AUTH_KEYS="$SSH_DIR/authorized_keys"
# Avoid duplicates
if grep -Fxq "$PUB_KEY" "$AUTH_KEYS" 2>/dev/null; then
    echo "Key already present in authorized_keys"
else
    echo "$PUB_KEY" >> "$AUTH_KEYS"
    chmod 600 "$AUTH_KEYS"
    echo "Key appended to authorized_keys"
fi

# 8️⃣ Test SSH authentication against GitHub
log "Testing SSH authentication to GitHub"
ssh -i "$KEY_PATH" -T git@github.com || true  # GitHub returns a welcome message, not an error code

# 9️⃣ (Optional) Switch the repo remote from HTTPS to SSH
if [[ -d "moria-homelab/.git" ]]; then
    log "Switching repository remote to SSH"
    pushd moria-homelab >/dev/null
    git remote set-url origin "$REPO_SSH_URL"
    git remote -v
    popd >/dev/null
else
    echo "Repository directory 'moria-homelab' not found – skip remote switch."
fi

log "All done! You can now SSH from other trusted hosts using this key."
