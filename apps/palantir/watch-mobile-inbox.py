#!/usr/bin/env python3
"""
Watches apps/palantir/mobile_inbox.jsonl for a new message from the user's phone
and exits 0 with the message payload to trigger Antigravity Reactive Wakeup.
"""
import json
import time
from pathlib import Path

INBOX = Path(__file__).parent / "mobile_inbox.jsonl"


def read_lines() -> list[str]:
    if not INBOX.exists():
        return []
    return [line.strip() for line in INBOX.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]


def main() -> None:
    initial_count = len(read_lines())
    while True:
        time.sleep(1.0)
        current = read_lines()
        if len(current) > initial_count:
            for raw in current[initial_count:]:
                try:
                    msg = json.loads(raw)
                    print(f"📲 NEW MOBILE MESSAGE ({msg.get('source', 'phone')}): {msg.get('text', '')}", flush=True)
                except Exception:
                    print(f"📲 NEW MOBILE MESSAGE: {raw}", flush=True)
            return


if __name__ == "__main__":
    main()
