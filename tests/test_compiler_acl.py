from __future__ import annotations

import unittest

from pt_agent.compiler.acl import (
    AclBinding,
    AclDefinition,
    AclEndpoint,
    AclRule,
    ExtendedAclRule,
    compile_acl_config,
)
from pt_agent.compiler.base import CommandCompileError


class AclCommandTests(unittest.TestCase):
    def test_compiles_extended_acl_with_ports_and_address_classes(self) -> None:
        plan = compile_acl_config(
            "CORE-A",
            AclDefinition(
                "105",
                (
                    ExtendedAclRule(
                        "permit",
                        "tcp",
                        AclEndpoint("network", "10.22.0.160", "0.0.0.15"),
                        AclEndpoint("host", "10.22.0.178"),
                        443,
                    ),
                    ExtendedAclRule(
                        "deny",
                        "ip",
                        AclEndpoint("network", "10.22.0.160", "0.0.0.15"),
                        AclEndpoint("any"),
                    ),
                ),
                kind="extended",
            ),
            [AclBinding("Vlan205", "in")],
        )
        self.assertIn(
            "access-list 105 permit tcp 10.22.0.160 0.0.0.15 "
            "host 10.22.0.178 eq 443",
            plan.commands,
        )
        self.assertIn(
            "access-list 105 deny ip 10.22.0.160 0.0.0.15 any",
            plan.commands,
        )
        self.assertEqual(plan.safety_issues(), [])

    def test_compiles_host_and_any_rules(self) -> None:
        plan = compile_acl_config(
            "R1",
            AclDefinition(
                "10",
                (
                    AclRule("deny", "host", "192.168.10.10"),
                    AclRule("permit", "any"),
                ),
            ),
            [AclBinding("GigabitEthernet0/1", "out")],
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn(
            "access-list 10 deny host 192.168.10.10",
            plan.commands,
        )
        self.assertIn("access-list 10 permit any", plan.commands)
        self.assertIn("ip access-group 10 out", plan.commands)

    def test_compiles_network_wildcard(self) -> None:
        plan = compile_acl_config(
            "R1",
            AclDefinition(
                "20",
                (
                    AclRule(
                        "deny",
                        "network",
                        "192.168.10.0",
                        "0.0.0.255",
                    ),
                    AclRule("permit", "any"),
                ),
            ),
            [AclBinding("GigabitEthernet0/0", "in")],
        )
        self.assertIn(
            "access-list 20 deny 192.168.10.0 0.0.0.255",
            plan.commands,
        )

    def test_rejects_non_contiguous_wildcard(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "not contiguous"):
            AclRule(
                "deny",
                "network",
                "192.168.10.0",
                "0.0.0.254",
            ).rendered()

    def test_rejects_bad_acl_id_and_direction(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "standard ACL ID"):
            AclDefinition("100", (AclRule("permit", "any"),)).rendered_id()
        with self.assertRaisesRegex(CommandCompileError, "direction"):
            AclBinding("GigabitEthernet0/1", "sideways").rendered()  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
