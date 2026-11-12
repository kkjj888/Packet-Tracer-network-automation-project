from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.rip import RipConfig, compile_rip_config


class RipCommandTests(unittest.TestCase):
    def test_compiles_ripv1(self) -> None:
        plan = compile_rip_config(
            "R1",
            RipConfig(1, ("172.16.0.0", "10.0.0.0")),
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn("version 1", plan.commands)
        self.assertIn("auto-summary", plan.commands)
        self.assertIn("network 172.16.0.0", plan.commands)
        self.assertEqual(plan.commands.count("end"), 1)

    def test_compiles_ripv2_without_auto_summary(self) -> None:
        plan = compile_rip_config(
            "R1",
            RipConfig(2, ("172.16.0.0",), auto_summary=False),
        )
        self.assertIn("version 2", plan.commands)
        self.assertIn("no auto-summary", plan.commands)
        self.assertEqual(plan.commands.count("end"), 1)

    def test_rejects_ripv1_without_auto_summary(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "RIPv1"):
            compile_rip_config(
                "R1",
                RipConfig(1, ("172.16.0.0",), auto_summary=False),
            )

    def test_rejects_invalid_and_duplicate_networks(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "invalid RIP network"):
            compile_rip_config("R1", RipConfig(2, ("not-an-ip",)))
        with self.assertRaisesRegex(CommandCompileError, "duplicated"):
            compile_rip_config(
                "R1",
                RipConfig(2, ("172.16.0.0", "172.16.0.0")),
            )


if __name__ == "__main__":
    unittest.main()
