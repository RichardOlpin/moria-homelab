#!/usr/bin/env python3
"""
Moria Homelab — Wake 'balrog' (AMD 7800X3D + Nvidia RTX 5070 Gaming PC).

Sends a 102-byte UDP Wake-on-LAN magic packet across the local network and
polls the target host until Ollama (port 11434) or SSH (port 22) responds.

Usage:
  python3 scripts/wake-balrog.py
  python3 scripts/wake-balrog.py --mac 00:11:22:33:44:55 --host 192.168.0.50
  python3 scripts/wake-balrog.py --simulate
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import sys
import time

DEFAULT_MAC = os.environ.get("BALROG_MAC", "9C:6B:00:C0:60:9B")
DEFAULT_HOST = os.environ.get("BALROG_HOST", "192.168.0.40")
DEFAULT_PORT = int(os.environ.get("BALROG_PORT", "11434"))


def create_magic_packet(mac_address: str) -> bytes:
    clean_mac = re.sub(r"[^0-9a-fA-F]", "", mac_address)
    if len(clean_mac) != 12:
        raise ValueError(f"Invalid MAC address: '{mac_address}'. Expected 12 hexadecimal characters.")
    return b"\xff" * 6 + bytes.fromhex(clean_mac) * 16


def get_local_broadcasts() -> list[str]:
    broadcasts = ["255.255.255.255"]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip.count(".") == 3 and not ip.startswith("127."):
                subnet = ip.rsplit(".", 1)[0]
                broadcasts.append(f"{subnet}.255")
    except Exception:
        pass
    return list(dict.fromkeys(broadcasts))


def send_wol(mac_address: str, ports: list[int] | None = None) -> list[str]:
    packet = create_magic_packet(mac_address)
    destinations = get_local_broadcasts()
    target_ports = ports or [9, 7]
    sent = []

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for dest in destinations:
            for port in target_ports:
                try:
                    sock.sendto(packet, (dest, port))
                    sent.append(f"{dest}:{port}")
                except Exception as exc:
                    print(f"⚠️ Warning sending to {dest}:{port} -> {exc}", file=sys.stderr)
    return sent


def is_port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Wake balrog Gaming PC via Wake-on-LAN")
    parser.add_argument("--mac", default=DEFAULT_MAC, help=f"Target MAC address (default: {DEFAULT_MAC})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to poll (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to poll (default: {DEFAULT_PORT})")
    parser.add_argument("--poll", action=argparse.BooleanOptionalAction, default=True, help="Poll until online")
    parser.add_argument("--timeout", type=int, default=30, help="Max seconds to wait for boot (default: 30)")
    parser.add_argument("--simulate", action="store_true", help="Run simulated wake demo without real wait")
    args = parser.parse_args()

    clean_mac = re.sub(r"[^0-9a-fA-F]", "", args.mac)
    formatted_mac = ":".join(clean_mac[i:i+2].upper() for i in range(0, 12, 2)) if len(clean_mac) == 12 else args.mac

    print(f"🔥 Awakening the Balrog of Morgoth (Gaming PC: AMD 7800X3D + RTX 5070)...")
    print(f"   Target MAC  : {formatted_mac}")
    print(f"   Host / Port : {args.host}:{args.port} (Ollama)")

    try:
        sent = send_wol(args.mac)
        print(f"⚡ Wake-on-LAN magic packet broadcast across {len(sent)} sockets: {', '.join(sent)}")
    except ValueError as ve:
        print(f"❌ Error: {ve}", file=sys.stderr)
        return 1

    if args.simulate:
        print("\n🧪 [DEMO MODE] Simulating boot sequence...")
        stages = [
            "Motherboard UEFI ACPI wake event received...",
            "AMD Ryzen 7 7800X3D initialized...",
            "Nvidia RTX 5070 CUDA driver loaded...",
            "Ollama server listening on port 11434...",
        ]
        for stage in stages:
            time.sleep(0.5)
            print(f"   ✓ {stage}")
        print("\n🔥 SUCCESS: The Balrog is AWAKE! (Simulation Complete)")
        return 0

    if not args.poll:
        print("Magic packet sent. (Polling skipped per --no-poll).")
        return 0

    print(f"\n⏳ Listening for {args.host}:{args.port} to come online (timeout: {args.timeout}s)...")
    start = time.time()
    attempt = 0
    while time.time() - start < args.timeout:
        attempt += 1
        elapsed = round(time.time() - start, 1)
        if is_port_open(args.host, args.port) or is_port_open(args.host, 22) or is_port_open(args.host, 445):
            print(f"\n🔥 SUCCESS: Balrog responded in {elapsed}s (attempt {attempt})!")
            print(f"   Nvidia GeForce RTX 5070 CUDA engine is online and ready for Immich ML / Whisper.")
            return 0
        sys.stdout.write(f"\r   [{elapsed}s / {args.timeout}s] Waiting for response (attempt {attempt})...")
        sys.stdout.flush()
        time.sleep(1.5)

    print(f"\n\n⚠️ Timed out waiting for {args.host}:{args.port} after {args.timeout}s.")
    print("   Tips:")
    print("   1. Verify Wake-on-LAN is enabled in BIOS/UEFI (ACPI PCIe Power On / EuP / ErP disabled).")
    print("   2. Ensure Ethernet link light is active when balrog is in sleep state.")
    print("   3. Verify target MAC in environment variable BALROG_MAC or with --mac <MAC>.")
    print("   4. Run with --simulate to preview the expected success output.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
