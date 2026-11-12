from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.static_routing import (
    StaticRoute,
    compile_static_routes,
)


class StaticRoutingCommandTests(unittest.TestCase):
    def test_compiles_default_and_specific_routes(self) -> None:
        plan = compile_static_routes(
            "R1",
            [
                StaticRoute("0.0.0.0/0", "10.0.0.2"),
                StaticRoute("192.168.20.0/24", "10.0.0.2", 10),
            ],
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn("ip route 0.0.0.0 0.0.0.0 10.0.0.2", plan.commands)
        self.assertIn(
            "ip route 192.168.20.0 255.255.255.0 10.0.0.2 10",
            plan.commands,
        )
        self.assertIn("show ip route", plan.commands)

    def test_rejects_host_bits(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "invalid static route"):
            StaticRoute("192.168.20.1/24", "10.0.0.2").rendered()

    def test_rejects_invalid_distance(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "distance"):
            StaticRoute("192.168.20.0/24", "10.0.0.2", 0).rendered()

    def test_rejects_duplicate_route(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "duplicated"):
            compile_static_routes(
                "R1",
                [
                    StaticRoute("10.0.0.0/8", "192.0.2.1"),
                    StaticRoute("10.0.0.0/8", "192.0.2.1", 5),
                ],
            )


if __name__ == "__main__":
    unittest.main()
