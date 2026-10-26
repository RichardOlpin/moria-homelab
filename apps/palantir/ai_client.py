#!/usr/bin/env python3
"""
Moria Homelab — On-Demand Auto-Waking AI Client for 'balrog'.

Connects to LM Studio (port 1234) or Ollama (port 11434) on balrog.
If balrog is sleeping, it AUTOMATICALLY broadcasts a Wake-on-LAN magic packet,
waits for the RTX 5070 to initialize, and executes the inference request.
Zero human intervention required.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Try importing send_wake_on_lan from server or scripts
try:
    from server import send_wake_on_lan
except ImportError:
    try:
        from wake_balrog import send_wol as _send_wol

        def send_wake_on_lan(mac: str) -> dict:
            return {"status": "sent", "sent_to": _send_wol(mac)}
    except ImportError:
        def send_wake_on_lan(mac: str) -> dict:
            clean = re.sub(r"[^0-9a-fA-F]", "", mac)
            pkt = b"\xff" * 6 + bytes.fromhex(clean) * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(pkt, ("255.255.255.255", 9))
                s.sendto(pkt, ("192.168.0.255", 9))
            return {"status": "sent", "sent_to": ["255.255.255.255:9", "192.168.0.255:9"]}

BALROG_MAC = os.environ.get("BALROG_MAC", "9C:6B:00:C0:60:9B")
BALROG_HOST = os.environ.get("BALROG_HOST", "192.168.0.40")
LM_STUDIO_PORT = int(os.environ.get("LM_STUDIO_PORT", "1234"))
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, OSError):
        return False


def ensure_balrog_awake(timeout: float = 30.0) -> tuple[bool, str]:
    """Checks if balrog is awake; if asleep, sends WoL packet and waits for it to boot."""
    # Check if either LM Studio or Ollama is already online
    if is_port_open(BALROG_HOST, LM_STUDIO_PORT) or is_port_open(BALROG_HOST, OLLAMA_PORT):
        return False, "already_online"

    # Also check if Windows is responding (port 445 / 22)
    was_completely_cold = not (is_port_open(BALROG_HOST, 445) or is_port_open(BALROG_HOST, 22))

    print(f"⚡ [Auto-Wake] balrog is sleeping. Broadcasting Wake-on-LAN magic packet to {BALROG_MAC}...")
    send_wake_on_lan(BALROG_MAC)

    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(BALROG_HOST, LM_STUDIO_PORT) or is_port_open(BALROG_HOST, OLLAMA_PORT) or is_port_open(BALROG_HOST, 445):
            elapsed = round(time.time() - start, 1)
            print(f"🔥 [Auto-Wake] balrog awakened and online in {elapsed}s!")
            return True, "woken"
        time.sleep(1.5)

    return False, "timeout"


def get_available_models() -> dict:
    """Discovers available models from LM Studio and Ollama on balrog."""
    results = {"lm_studio": [], "ollama": []}

    # 1. Check LM Studio (:1234)
    if is_port_open(BALROG_HOST, LM_STUDIO_PORT):
        try:
            req = urllib.request.Request(f"http://{BALROG_HOST}:{LM_STUDIO_PORT}/v1/models")
            with urllib.request.urlopen(req, timeout=2.0) as r:
                data = json.loads(r.read())
                results["lm_studio"] = [m.get("id") for m in data.get("data", [])]
        except Exception:
            pass

    # 2. Check Ollama (:11434)
    if is_port_open(BALROG_HOST, OLLAMA_PORT):
        try:
            req = urllib.request.Request(f"http://{BALROG_HOST}:{OLLAMA_PORT}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as r:
                data = json.loads(r.read())
                results["ollama"] = [m.get("name") for m in data.get("models", [])]
        except Exception:
            pass

    return results


def query_balrog_ai(
    prompt: str,
    system_prompt: str = "You are the Palantír AI assistant running on Moria Homelab.",
    model: str | None = None,
    timeout: float = 60.0,
    auto_wake: bool = True,
) -> dict:
    """Executes a chat completion on balrog, auto-waking the PC via WoL if asleep."""
    was_woken = False
    if auto_wake:
        woken, status = ensure_balrog_awake(timeout=25.0)
        was_woken = woken

    # 1. Try LM Studio first (OpenAI compatible)
    if is_port_open(BALROG_HOST, LM_STUDIO_PORT):
        target_model = model
        if not target_model:
            models = get_available_models()["lm_studio"]
            target_model = models[0] if models else "local-model"

        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        }
        try:
            req = urllib.request.Request(
                f"http://{BALROG_HOST}:{LM_STUDIO_PORT}/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"]
                return {
                    "backend": "lm-studio",
                    "model": target_model,
                    "content": content,
                    "woken": was_woken,
                    "host": f"{BALROG_HOST}:{LM_STUDIO_PORT}",
                }
        except Exception as exc:
            print(f"⚠️ LM Studio query failed: {exc}", file=sys.stderr)

    # 2. Try Ollama (:11434)
    if is_port_open(BALROG_HOST, OLLAMA_PORT):
        target_model = model or "llama3.2"
        payload = {
            "model": target_model,
            "prompt": f"{system_prompt}\n\nUser: {prompt}\nAssistant:",
            "stream": False,
        }
        try:
            req = urllib.request.Request(
                f"http://{BALROG_HOST}:{OLLAMA_PORT}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                return {
                    "backend": "ollama",
                    "model": target_model,
                    "content": data.get("response", ""),
                    "woken": was_woken,
                    "host": f"{BALROG_HOST}:{OLLAMA_PORT}",
                }
        except Exception as exc:
            print(f"⚠️ Ollama query failed: {exc}", file=sys.stderr)

    return {
        "error": f"balrog is reachable, but neither LM Studio (port {LM_STUDIO_PORT}) nor Ollama (port {OLLAMA_PORT}) is serving requests.",
        "woken": was_woken,
        "host": BALROG_HOST,
    }


if __name__ == "__main__":
    test_prompt = sys.argv[1] if len(sys.argv) > 1 else "Hello from Moria! Describe the Balrog in one epic sentence."
    print(f"Testing Balrog AI Client with prompt: '{test_prompt}'")
    res = query_balrog_ai(test_prompt)
    print(json.dumps(res, indent=2))
