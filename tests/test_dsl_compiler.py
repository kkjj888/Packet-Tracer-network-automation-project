from __future__ import annotations

import copy
import unittest
from pathlib import Path

from pt_agent.dsl_compiler import (
    DslCompileError,
    compile_network_dsl,
    topology_js,
)
from pt_agent.validation import load_yaml_document


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DslCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.campus = load_yaml_document(
            PROJECT_ROOT / "examples" / "campus-vlan.yaml"
        )
        self.ospf = load_yaml_document(
            PROJECT_ROOT / "examples" / "ospf-routing.yaml"
        )

    def test_compiles_vlan_trunk_document(self) -> None:
        network = compile_network_dsl(self.campus)
        self.assertEqual(network.project, "campus-vlan-segmentation")
        self.assertEqual(len(network.devices), 5)
        self.assertEqual(len(network.links), 4)
        self.assertEqual(len(network.host_addresses), 3)
        self.assertEqual(len(network.command_plans), 4)
        self.assertEqual(
            [(plan.device, plan.module) for plan in network.command_plans],
            [
                ("sw1", "vlan"),
                ("sw1", "trunk"),
                ("sw2", "vlan"),
                ("sw2", "trunk"),
            ],
        )
        self.assertEqual(len(network.verification), 2)
        self.assertTrue(
            all(not plan.safety_issues() for plan in network.command_plans)
        )

    def test_compiles_routed_ospf_document(self) -> None:
        network = compile_network_dsl(self.ospf)
        self.assertEqual(len(network.host_addresses), 2)
        modules = [plan.module for plan in network.command_plans]
        self.assertEqual(modules.count("interface-ipv4"), 2)
        self.assertEqual(modules.count("ospf"), 2)
        ospf_commands = [
            command
            for plan in network.command_plans
            if plan.module == "ospf"
            for command in plan.commands
        ]
        self.assertIn(
            "network 172.16.10.0 0.0.0.255 area 0",
            ospf_commands,
        )
        self.assertIn("network 10.0.0.0 0.0.0.3 area 0", ospf_commands)
        self.assertTrue(
            all(not plan.safety_issues() for plan in network.command_plans)
        )

    def test_topology_js_contains_devices_and_links(self) -> None:
        script = topology_js(compile_network_dsl(self.campus))
        self.assertIn("addDevice", script)
        self.assertIn("createLink", script)
        self.assertIn('"id":"sw1"', script)
        self.assertIn('"from":"pc1:FastEthernet0"', script)

    def test_invalid_document_is_rejected_before_compilation(self) -> None:
        document = copy.deepcopy(self.ospf)
        document["ipv4"][0]["gateway"] = "10.10.10.1"
        with self.assertRaisesRegex(DslCompileError, "validation failed"):
            compile_network_dsl(document)

    def test_server_device_is_supported_as_host(self) -> None:
        document = copy.deepcopy(self.campus)
        document["devices"][2]["type"] = "server"
        document["devices"][2]["model"] = "Server-PT"
        network = compile_network_dsl(document)
        server = next(
            item for item in network.devices if item.device_id == "pc1"
        )
        self.assertEqual(server.device_type, "server")
        self.assertTrue(
            any(item.device == "pc1" for item in network.host_addresses)
        )


if __name__ == "__main__":
    unittest.main()
