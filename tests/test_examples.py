from __future__ import annotations

import unittest
from pathlib import Path

from pt_agent.dsl_compiler import compile_network_dsl
from pt_agent.validation import NetworkValidator, load_yaml_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_ROOT / "examples"


class ExampleDslTests(unittest.TestCase):
    def test_every_example_validates_and_compiles(self) -> None:
        files = sorted(EXAMPLES.glob("*.yaml"))
        self.assertGreaterEqual(len(files), 6)
        validator = NetworkValidator()
        for path in files:
            with self.subTest(path=path.name):
                document = load_yaml_document(path)
                result = validator.validate(document)
                self.assertTrue(result.valid, result.to_dict())
                network = compile_network_dsl(document)
                self.assertTrue(network.devices)
                self.assertTrue(network.links)
                self.assertTrue(network.verification)
                for plan in network.command_plans:
                    self.assertEqual(plan.safety_issues(), [])

    def test_expected_module_coverage(self) -> None:
        coverage: set[str] = set()
        for path in EXAMPLES.glob("*.yaml"):
            network = compile_network_dsl(load_yaml_document(path))
            coverage.update(plan.module for plan in network.command_plans)
        self.assertTrue(
            {
                "interface-ipv4",
                "vlan",
                "trunk",
                "acl",
                "static-routing",
                "rip",
                "ospf",
            }.issubset(coverage)
        )


if __name__ == "__main__":
    unittest.main()
