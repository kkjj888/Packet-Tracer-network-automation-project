from __future__ import annotations

import unittest
from pathlib import Path

from pt_agent.dsl_compiler import compile_network_dsl
from pt_agent.validation import NetworkValidator, load_yaml_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT = PROJECT_ROOT / "examples" / "assignment"


class AssignmentCaseTests(unittest.TestCase):
    def test_all_valid_assignment_cases_compile_safely(self) -> None:
        files = sorted(ASSIGNMENT.glob("uc*.yaml"))
        self.assertGreaterEqual(len(files), 14)
        for path in files:
            if path.name == "uc12-invalid-allocation.yaml":
                continue
            with self.subTest(path=path.name):
                document = load_yaml_document(path)
                result = NetworkValidator().validate(document)
                self.assertTrue(result.valid, result.to_dict())
                network = compile_network_dsl(document)
                self.assertTrue(network.verification)
                for plan in network.command_plans:
                    self.assertEqual(plan.safety_issues(), [])

    def test_uc05_matrix_expands_to_all_directed_pairs(self) -> None:
        network = compile_network_dsl(
            load_yaml_document(
                ASSIGNMENT / "uc05a-router-on-a-stick.yaml"
            )
        )
        self.assertEqual(len(network.verification), 30)

    def test_uc08_has_explicit_post_failure_assertions(self) -> None:
        network = compile_network_dsl(
            load_yaml_document(ASSIGNMENT / "uc08-dual-isp-failover.yaml")
        )
        self.assertTrue(network.failure_verification)
        self.assertTrue(network.failure_route_assertions)
        self.assertTrue(network.failure_traceroutes)

    def test_uc10_compiles_ipv6_tunnel_and_ping6(self) -> None:
        network = compile_network_dsl(
            load_yaml_document(ASSIGNMENT / "uc10-ipv6-over-ipv4.yaml")
        )
        self.assertTrue(network.host_ipv6_addresses)
        self.assertTrue(
            any(plan.module == "ipv6-gre" for plan in network.command_plans)
        )
        self.assertEqual(network.verification[0].protocol, "ping6")

    def test_uc12_is_rejected_as_impossible_allocation(self) -> None:
        result = NetworkValidator().validate(
            load_yaml_document(
                ASSIGNMENT / "uc12-invalid-allocation.yaml"
            )
        )
        self.assertFalse(result.valid)
        self.assertIn(
            "CHILD_NETWORK_OUTSIDE_PARENT",
            {issue.code for issue in result.issues},
        )


if __name__ == "__main__":
    unittest.main()
