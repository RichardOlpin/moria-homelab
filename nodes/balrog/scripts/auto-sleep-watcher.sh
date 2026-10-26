#!/usr/bin/env bash
# ==============================================================================
# 'balrog' Auto-Sleep Idle Watcher (AMD 7800X3D + Nvidia RTX 5070)
#
# When 'balrog' is woken via Wake-on-LAN by 'gandalf' or 'erebor' to run heavy
# GPU tasks (Immich ML, Whisper subtitles, Ollama embeddings), this watcher
# monitors GPU utilization and active sessions. Once GPU utilization stays
# below 10% for IDLE_MINUTES (default: 20m) with no active SSH/gaming session,
# it automatically puts 'balrog' back to sleep to save ~80W–120W of idle power.
# ==============================================================================
set -euo pipefail

IDLE_MINUTES="${IDLE_MINUTES:-20}"
GPU_THRESHOLD="${GPU_THRESHOLD:-10}"
idle_counter=0

echo "==> Starting balrog Auto-Sleep Watcher (Idle threshold: ${IDLE_MINUTES}m at <${GPU_THRESHOLD}% GPU)..."

while true; do
    sleep 60

    # 1. Check RTX 5070 GPU utilization via nvidia-smi
    gpu_util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d ' ' || echo "0")

    # 2. Check if any interactive SSH session or active game process is running
    active_ssh=$(who | wc -l | tr -d ' ')

    if (( gpu_util >= GPU_THRESHOLD )) || (( active_ssh > 0 )); then
        if (( idle_counter > 0 )); then
            echo "[$(date +%H:%M:%S)] Activity detected (GPU: ${gpu_util}%, SSH users: ${active_ssh}). Resetting idle timer."
        fi
        idle_counter=0
    else
        idle_counter=$((idle_counter + 1))
        echo "[$(date +%H:%M:%S)] Idle minute ${idle_counter}/${IDLE_MINUTES} (GPU: ${gpu_util}%)"
    fi

    if (( idle_counter >= IDLE_MINUTES )); then
        echo "==> 'balrog' has been idle for ${IDLE_MINUTES} minutes. Returning to the shadow (suspending)..."
        idle_counter=0
        if grep -qi microsoft /proc/version 2>/dev/null; then
            # Running inside WSL2 on Windows Gaming PC
            powershell.exe -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', \$false, \$false)"
        else
            # Native Linux
            systemctl suspend
        fi
    fi
done
