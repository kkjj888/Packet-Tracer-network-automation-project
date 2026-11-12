from __future__ import annotations

import unittest
from pathlib import Path

from pt_agent.dsl_compiler import compile_network_dsl
from pt_agent.dsl_deployment import (
    DslDeploymentError,
    destination_ip,
    evaluate_route_assertion,
    evaluate_traceroute,
    evaluate_verification,
    host_ip_by_device,
    parse_traceroute_hops,
)
from pt_agent.dsl_compiler import RouteAssertionSpec, TracerouteSpec
from pt_agent.validation import load_yaml_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DslDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = compile_network_dsl(
            load_yaml_document(
                PROJECT_ROOT / "examples" / "campus-vlan.yaml"
            )
        )

    def test_maps_host_names_to_ip_addresses(self) -> None:
        addresses = host_ip_by_device(self.network)
        self.assertEqual(addresses["pc1"], "192.168.10.10")
        self.assertEqual(addresses["pc2"], "192.168.10.11")
        self.assertEqual(destination_ip(self.network, "pc3"), "192.168.20.20")

    def test_evaluates_expected_pass(self) -> None:
        spec = self.network.verification[0]
        result = evaluate_verification(
            spec,
            {
                "success": True,
                "complete": True,
                "sent": 4,
                "received": 4,
            },
            "192.168.10.11",
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.actual, "pass")

    def test_evaluates_expected_failure(self) -> None:
        spec = self.network.verification[1]
        result = evaluate_verification(
            spec,
            {
                "success": False,
                "complete": True,
                "sent": 4,
                "received": 0,
            },
            "192.168.20.20",
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.actual, "fail")

    def test_rejects_unknown_destination(self) -> None:
        with self.assertRaisesRegex(DslDeploymentError, "no IPv4 address"):
            destination_ip(self.network, "unknown")

    def test_route_assertion_matches_protocol_and_next_hop(self) -> None:
        result = evaluate_route_assertion(
            RouteAssertionSpec(
                "r1",
                "172.16.20.0/24",
                "ospf",
                "10.0.0.2",
                None,
                110,
            ),
            {
                "networks": [
                    {
                        "network": "172.16.20.0",
                        "mask": "255.255.255.0",
                        "entries": [
                            {
                                "protocol": "79",
                                "nextHop": "10.0.0.2",
                                "port": "GigabitEthernet0/1",
                                "adminDistance": 110,
                            }
                        ],
                    }
                ]
            },
        )
        self.assertTrue(result.passed)

    def test_traceroute_parser_and_exact_path_assertion(self) -> None:
        output = (
            "Tracing route to 192.168.20.20\n"
            "  1    <1 ms    <1 ms    <1 ms  192.168.10.1\n"
            "  2    <1 ms    <1 ms    <1 ms  192.168.20.20\n"
            "Trace complete.\n"
        )
        self.assertEqual(
            parse_traceroute_hops(output),
            ("192.168.10.1", "192.168.20.20"),
        )
        result = evaluate_traceroute(
            TracerouteSpec(
                "inter-vlan-path",
                "pc1",
                "pc2",
                ("192.168.10.1", "192.168.20.20"),
            ),
            output,
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
