#!/usr/bin/env python3
"""
Unit tests for Moria Homelab Wake-on-LAN and Balrog status modules.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "palantir"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from server import send_wake_on_lan, check_balrog_status, BALROG_STATE
from wake_balrog import create_magic_packet, DEFAULT_MAC


class TestWakeBalrog(unittest.TestCase):
    def test_magic_packet_generation(self):
        packet = create_magic_packet("AA:BB:CC:DD:EE:FF")
        self.assertEqual(len(packet), 102)
        self.assertTrue(packet.startswith(b"\xff" * 6))
        # Verify 16 repetitions of the 6-byte MAC
        expected_mac = bytes.fromhex("AABBCCDDEEFF")
        self.assertEqual(packet[6:12], expected_mac)
        self.assertEqual(packet[96:102], expected_mac)

    def test_invalid_mac_raises(self):
        with self.assertRaises(ValueError):
            create_magic_packet("invalid-mac-address")
        with self.assertRaises(ValueError):
            create_magic_packet("AA:BB:CC")

    def test_send_wake_on_lan(self):
        # Broadcasts locally without error
        res = send_wake_on_lan("AA:BB:CC:DD:EE:FF")
        self.assertEqual(res["status"], "sent")
        self.assertEqual(res["mac"], "AA:BB:CC:DD:EE:FF")
        self.assertTrue(len(res["sent_to"]) >= 1)

    def test_balrog_status_simulated_flow(self):
        status_before = check_balrog_status()
        self.assertIn("online", status_before)
        self.assertIn("gpu", status_before)

        # Trigger simulated awake
        res = send_wake_on_lan("AA:BB:CC:DD:EE:FF")
        import time
        BALROG_STATE["simulated_wake_until"] = time.time() + 10

        status_after = check_balrog_status()
        self.assertTrue(status_after["online"])
        self.assertEqual(status_after["status"], "awake")
        self.assertTrue(status_after["simulated"])
        self.assertIn("RTX 5070", status_after["gpu"])

        # Reset
        BALROG_STATE["simulated_wake_until"] = 0.0

    def test_ai_client_model_discovery(self):
        from ai_client import get_available_models, is_port_open
        models = get_available_models()
        self.assertIn("lm_studio", models)
        self.assertIn("ollama", models)

    def test_put_balrog_to_sleep_offline_graceful(self):
        from ai_client import put_balrog_to_sleep
        # If webhook is not listening on test port, should return graceful error dict
        res = put_balrog_to_sleep(host="127.0.0.1", port=59999, timeout=0.1)
        self.assertEqual(res["status"], "error")
        self.assertIn("message", res)


if __name__ == "__main__":
    unittest.main()
