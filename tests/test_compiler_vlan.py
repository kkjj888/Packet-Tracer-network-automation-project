from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.vlan import (
    AccessPort,
    VlanDefinition,
    compile_vlan_config,
)


class VlanCommandTests(unittest.TestCase):
    def test_compiles_vlans_and_access_ports(self) -> None:
        plan = compile_vlan_config(
            "SW1",
            [
                VlanDefinition(10, "FINANCE"),
                VlanDefinition(20, "GUEST"),
            ],
            [
                AccessPort("FastEthernet0/1", 10),
                AccessPort("FastEthernet0/2", 20),
            ],
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn("vlan 10", plan.commands)
        self.assertIn("name FINANCE", plan.commands)
        self.assertIn("switchport access vlan 20", plan.commands)
        self.assertIn("show vlan brief", plan.commands)

    def test_allows_pt_default_vlan_one_for_access(self) -> None:
        plan = compile_vlan_config(
            "SW1",
            [VlanDefinition(10, "FINANCE")],
            [AccessPort("FastEthernet0/1", 1)],
        )
        self.assertIn("switchport access vlan 1", plan.commands)

    def test_rejects_duplicate_vlan_and_port(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "VLAN 10"):
            compile_vlan_config(
                "SW1",
                [VlanDefinition(10, "FINANCE"), VlanDefinition(10, "OTHER")],
            )
        with self.assertRaisesRegex(CommandCompileError, "access port"):
            compile_vlan_config(
                "SW1",
                [VlanDefinition(10, "FINANCE")],
                [
                    AccessPort("FastEthernet0/1", 10),
                    AccessPort("FastEthernet0/1", 10),
                ],
            )

    def test_rejects_undefined_vlan_and_bad_name(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "undefined VLAN 99"):
            compile_vlan_config(
                "SW1",
                [VlanDefinition(10, "FINANCE")],
                [AccessPort("FastEthernet0/1", 99)],
            )
        with self.assertRaisesRegex(CommandCompileError, "VLAN name"):
            compile_vlan_config("SW1", [VlanDefinition(10, "BAD NAME")])


if __name__ == "__main__":
    unittest.main()
