from __future__ import annotations

import unittest

from pt_agent.compiler.base import CommandCompileError
from pt_agent.compiler.ospf import (
    OspfNetwork,
    compile_ospf_config,
    wildcard_mask,
)


class OspfCommandTests(unittest.TestCase):
    def test_derives_wildcards_from_prefixes(self) -> None:
        self.assertEqual(wildcard_mask("172.16.10.0/24"), "0.0.0.255")
        self.assertEqual(wildcard_mask("10.0.0.0/30"), "0.0.0.3")

    def test_compiles_ospf_networks_and_areas(self) -> None:
        plan = compile_ospf_config(
            "R1",
            100,
            [
                OspfNetwork("172.16.10.0/24", 0),
                OspfNetwork("10.0.0.0/30", 0),
            ],
        )
        self.assertEqual(plan.safety_issues(), [])
        self.assertIn(
            "network 172.16.10.0 0.0.0.255 area 0",
            plan.commands,
        )
        self.assertIn("network 10.0.0.0 0.0.0.3 area 0", plan.commands)
        self.assertEqual(plan.commands.count("end"), 1)

    def test_rejects_network_with_host_bits(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "host bits"):
            OspfNetwork("172.16.10.10/24", 0).rendered()

    def test_rejects_invalid_process_and_duplicate_network(self) -> None:
        with self.assertRaisesRegex(CommandCompileError, "process ID"):
            compile_ospf_config(
                "R1",
                0,
                [OspfNetwork("10.0.0.0/30", 0)],
            )
        with self.assertRaisesRegex(CommandCompileError, "duplicated"):
            compile_ospf_config(
                "R1",
                100,
                [
                    OspfNetwork("10.0.0.0/30", 0),
                    OspfNetwork("10.0.0.0/30", 0),
                ],
            )


if __name__ == "__main__":
    unittest.main()
