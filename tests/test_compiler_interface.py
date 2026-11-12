from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.interface import (
    RouterInterface,
    RouterSubinterface,
    compile_ipv4_interfaces,
    compile_vlan_subinterfaces,
)


class InterfaceCommandTests(unittest.TestCase):
    def test_compiles_routed_interfaces(self) -> None:
        plan = compile_ipv4_interfaces(
            "R1",
            [
                RouterInterface("GigabitEthernet0/0", "192.168.10.1/24"),
                RouterInterface("GigabitEthernet0/1", "10.0.0.1/30"),
            ],
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn(
            "ip address 192.168.10.1 255.255.255.0",
            plan.commands,
        )
        self.assertIn(
            "ip address 10.0.0.1 255.255.255.252",
            plan.commands,
        )

    def test_rejects_duplicate_interfaces(self) -> None:
        with self.assertRaisesRegex(
            CommandCompileError, "interface .* duplicated"
        ):
            compile_ipv4_interfaces(
                "R1",
                [
                    RouterInterface("GigabitEthernet0/0", "10.0.0.1/30"),
                    RouterInterface("GigabitEthernet0/0", "10.0.1.1/30"),
                ],
            )

    def test_rejects_network_address_for_host_interface(self) -> None:
        with self.assertRaisesRegex(
            CommandCompileError,
            "not usable as an interface host address",
        ):
            compile_ipv4_interfaces(
                "R1",
                [RouterInterface("GigabitEthernet0/0", "192.168.1.0/24")],
            )

    def test_rejects_interface_injection(self) -> None:
        with self.assertRaisesRegex(
            CommandCompileError,
            "must not contain whitespace",
        ):
            compile_ipv4_interfaces(
                "R1",
                [RouterInterface("Gi0/0\nreload", "10.0.0.1/30")],
            )

    def test_compiles_router_on_a_stick(self) -> None:
        plan = compile_vlan_subinterfaces(
            "R1",
            [
                RouterSubinterface(
                    "GigabitEthernet0/0",
                    "GigabitEthernet0/0.10",
                    10,
                    "192.168.10.1/24",
                ),
                RouterSubinterface(
                    "GigabitEthernet0/0",
                    "GigabitEthernet0/0.20",
                    20,
                    "192.168.20.1/24",
                ),
            ],
        )
        self.assertIn("encapsulation dot1Q 10", plan.commands)
        self.assertIn("encapsulation dot1Q 20", plan.commands)
        self.assertEqual(plan.commands.count("interface GigabitEthernet0/0"), 1)

    def test_rejects_subinterface_vlan_mismatch_name(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "child"):
            compile_vlan_subinterfaces(
                "R1",
                [
                    RouterSubinterface(
                        "GigabitEthernet0/0",
                        "GigabitEthernet0/1.10",
                        10,
                        "192.168.10.1/24",
                    )
                ],
            )


if __name__ == "__main__":
    unittest.main()
