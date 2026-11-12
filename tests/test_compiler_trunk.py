from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.trunk import TrunkPort, compile_trunk_config


class TrunkCommandTests(unittest.TestCase):
    def test_compiles_allowed_vlan_ranges(self) -> None:
        plan = compile_trunk_config(
            "SW1",
            [
                TrunkPort(
                    "GigabitEthernet0/1",
                    native_vlan=1,
                    allowed_vlans=(1, 10, 11, 12, 20),
                )
            ],
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn("switchport mode trunk", plan.commands)
        self.assertIn(
            "switchport trunk allowed vlan 1,10-12,20",
            plan.commands,
        )
        self.assertIn("show interfaces trunk", plan.commands)

    def test_all_keyword_is_supported(self) -> None:
        plan = compile_trunk_config(
            "SW1",
            [TrunkPort("GigabitEthernet0/1")],
        )
        self.assertIn("switchport trunk allowed vlan all", plan.commands)

    def test_rejects_native_vlan_outside_allowed(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "native VLAN"):
            compile_trunk_config(
                "SW1",
                [
                    TrunkPort(
                        "GigabitEthernet0/1",
                        native_vlan=99,
                        allowed_vlans=(10, 20),
                    )
                ],
            )

    def test_rejects_duplicate_and_injected_ports(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "duplicated"):
            compile_trunk_config(
                "SW1",
                [
                    TrunkPort("GigabitEthernet0/1"),
                    TrunkPort("GigabitEthernet0/1"),
                ],
            )
        with self.assertRaisesRegex(CommandCompileError, "whitespace"):
            compile_trunk_config(
                "SW1",
                [TrunkPort("Gi0/1\nreload")],
            )


if __name__ == "__main__":
    unittest.main()
