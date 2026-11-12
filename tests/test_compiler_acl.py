from __future__ import annotations

import unittest

from pt_agent.compiler.acl import (
    AclBinding,
    AclDefinition,
    AclRule,
    compile_acl_config,
)
from pt_agent.compiler.base import CommandCompileError


class AclCommandTests(unittest.TestCase):
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
