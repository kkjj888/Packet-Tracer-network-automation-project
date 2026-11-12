from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.dhcp import DhcpPool, compile_dhcp_config


class DhcpCommandTests(unittest.TestCase):
    def test_compiles_dhcp_pool(self) -> None:
        plan = compile_dhcp_config(
            "R1",
            [
                DhcpPool(
                    "LAN",
                    "192.168.10.0/24",
                    "192.168.10.1",
                    ("192.168.10.1",),
                    ("192.168.10.1", "192.168.10.10"),
                )
            ],
        )
        self.assertIn("ip dhcp pool LAN", plan.commands)
        self.assertIn(
            "network 192.168.10.0 255.255.255.0",
            plan.commands,
        )
        self.assertIn("default-router 192.168.10.1", plan.commands)
        self.assertIn(
            "ip dhcp excluded-address 192.168.10.10 192.168.10.10",
            plan.commands,
        )
        self.assertEqual(plan.safety_issues(), [])

    def test_rejects_router_outside_network(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "outside"):
            compile_dhcp_config(
                "R1",
                [DhcpPool("LAN", "192.168.10.0/24", "192.168.20.1")],
            )

    def test_rejects_duplicate_pool(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "duplicated"):
            compile_dhcp_config(
                "R1",
                [
                    DhcpPool("LAN", "192.168.10.0/24", "192.168.10.1"),
                    DhcpPool("lan", "192.168.20.0/24", "192.168.20.1"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
