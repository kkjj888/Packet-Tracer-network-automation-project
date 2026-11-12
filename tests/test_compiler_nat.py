from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.nat import (
    PatConfig,
    StaticNatConfig,
    compile_pat_config,
    compile_static_nat_config,
)


class NatCommandTests(unittest.TestCase):
    def test_compiles_static_tcp_nat(self) -> None:
        plan = compile_static_nat_config(
            "HQ-R1",
            [
                StaticNatConfig(
                    "tcp",
                    "10.22.0.178",
                    80,
                    "192.0.2.145",
                    80,
                    ("GigabitEthernet0/0",),
                    "Serial0/0/0",
                )
            ],
        )
        self.assertIn(
            "ip nat inside source static tcp 10.22.0.178 80 "
            "192.0.2.145 80",
            plan.commands,
        )
        self.assertEqual(plan.safety_issues(), [])

    def test_compiles_pat_configuration(self) -> None:
        plan = compile_pat_config(
            "R1",
            [
                PatConfig(
                    "1",
                    "192.168.0.0/24",
                    ("GigabitEthernet0/0",),
                    "GigabitEthernet0/1",
                )
            ],
        )
        self.assertIn(
            "access-list 1 permit 192.168.0.0 0.0.0.255",
            plan.commands,
        )
        self.assertIn("ip nat inside", plan.commands)
        self.assertIn("ip nat outside", plan.commands)
        self.assertIn(
            "ip nat inside source list 1 interface GigabitEthernet0/1 overload",
            plan.commands,
        )
        self.assertEqual(plan.safety_issues(), [])

    def test_rejects_inside_outside_overlap(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "outside"):
            compile_pat_config(
                "R1",
                [
                    PatConfig(
                        "1",
                        "192.168.0.0/24",
                        ("GigabitEthernet0/0",),
                        "GigabitEthernet0/0",
                    )
                ],
            )

    def test_rejects_bad_acl_and_duplicate(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "ACL ID"):
            compile_pat_config(
                "R1",
                [
                    PatConfig(
                        "100",
                        "192.168.0.0/24",
                        ("GigabitEthernet0/0",),
                        "GigabitEthernet0/1",
                    )
                ],
            )
        with self.assertRaisesRegex(CommandCompileError, "duplicated"):
            compile_pat_config(
                "R1",
                [
                    PatConfig(
                        "1",
                        "192.168.0.0/24",
                        ("GigabitEthernet0/0",),
                        "GigabitEthernet0/1",
                    ),
                    PatConfig(
                        "1",
                        "192.168.1.0/24",
                        ("GigabitEthernet0/2",),
                        "GigabitEthernet0/1",
                    ),
                ],
            )


if __name__ == "__main__":
    unittest.main()
