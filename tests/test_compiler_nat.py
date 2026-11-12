from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.nat import PatConfig, compile_pat_config


class NatCommandTests(unittest.TestCase):
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
