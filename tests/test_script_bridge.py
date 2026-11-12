from __future__ import annotations

import unittest
from pathlib import Path

from pt_agent.script_backend import (
    configure_acl_js,
    configure_host_ip_js,
    configure_switch_vlans_js,
    configure_trunk_port_js,
    minimal_topology_js,
    routing_state_js,
    save_project_js,
    set_port_power_js,
    topology_state_js,
)
from pt_agent.script_bridge import decode_result_hex, wrap_expression
from pt_agent.cli import parse_ping_output
from pt_agent.cli import _parse_acl_output, _parse_vlan_output
from pt_agent.config_suite import rip_config_commands
from pt_agent.diagnostics import diagnose_host_address


class ScriptBridgeTests(unittest.TestCase):
    def test_wrap_expression(self) -> None:
        wrapped = wrap_expression('return "hello";', 54321)
        self.assertTrue(wrapped.startswith("__mcpEval("))
        self.assertIn(",54321);", wrapped)

    def test_decode_result(self) -> None:
        text = '{"ok":true}'
        encoded = text.encode("utf-8").hex()
        self.assertEqual(decode_result_hex(encoded), text)

    def test_generated_topology_uses_native_api(self) -> None:
        script = minimal_topology_js()
        self.assertIn("getLogicalWorkspace()", script)
        self.assertIn("addDevice(8,\"PC-PT\"", script)
        self.assertIn("addDevice(1,\"2960-24TT\"", script)
        self.assertIn("createLink(", script)

    def test_state_reader_and_save(self) -> None:
        self.assertIn("getDeviceCount()", topology_state_js())
        script = save_project_js(Path("x.pkt"))
        self.assertIn("fileSaveAsNoPrompt", script)
        self.assertIn("x.pkt", script)

    def test_host_config_command(self) -> None:
        script = configure_host_ip_js(
            "PC1", "FastEthernet0", "192.168.1.10", "255.255.255.0"
        )
        self.assertIn('setIpSubnetMask("192.168.1.10","255.255.255.0")', script)
        self.assertIn("getIpAddress()", script)

    def test_parse_successful_ping(self) -> None:
        output = (
            "Pinging 192.168.1.11 with 32 bytes of data:\r\n"
            "Reply from 192.168.1.11: bytes=32 time<1ms TTL=128\r\n"
            "Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),\r\n"
            "Approximate round trip times in milli-seconds:\r\n"
            "Minimum = 0ms, Maximum = 0ms, Average = 0ms"
        )
        result = parse_ping_output(output)
        self.assertTrue(result["success"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["sent"], 4)
        self.assertEqual(result["received"], 4)

    def test_partial_ping_is_not_a_false_success(self) -> None:
        output = (
            "Pinging 192.168.1.11 with 32 bytes of data:\r\n"
            "Request timed out.\r\n"
            "Request timed out.\r\n"
            "Reply from 192.168.1.11: bytes=32 time<1ms TTL=128\r\n"
        )
        result = parse_ping_output(output)
        self.assertFalse(result["success"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["sent"], 3)

    def test_diagnose_host_mask_mismatch(self) -> None:
        diagnosis = diagnose_host_address(
            expected={
                "device": "PC1",
                "port": "FastEthernet0",
                "ip": "192.168.1.10",
                "mask": "255.255.255.0",
            },
            observed={
                "device": "PC1",
                "port": "FastEthernet0",
                "ip": "192.168.1.10",
                "mask": "255.255.255.252",
            },
            peer_ip="192.168.1.20",
        )
        self.assertIsNotNone(diagnosis)
        self.assertEqual(diagnosis.code, "HOST_MASK_MISMATCH")
        self.assertEqual(diagnosis.device, "PC1")

    def test_parse_vlan_assignments(self) -> None:
        output = (
            "10   FINANCE   active    Fa0/1, Fa0/2\n"
            "20   GUEST     active    Fa0/3\n"
        )
        parsed = _parse_vlan_output(output)
        self.assertTrue(parsed["pc1_in_vlan10"])
        self.assertTrue(parsed["pc2_in_vlan10"])
        self.assertTrue(parsed["pc3_in_vlan20"])

    def test_parse_acl_rules(self) -> None:
        parsed = _parse_acl_output(
            "10 deny host 192.168.10.10\n20 permit any"
        )
        self.assertTrue(parsed["deny_pc1"])
        self.assertTrue(parsed["permit_any"])

    def test_vlan_configuration_uses_structured_api(self) -> None:
        script = configure_switch_vlans_js(
            "SW1", {10: "FINANCE"}, {"FastEthernet0/1": 10}
        )
        self.assertIn('getProcess("VlanManager")', script)
        self.assertIn("setAccessVlan", script)
        self.assertIn("getAccessVlan", script)

    def test_trunk_configuration_sets_admin_mode(self) -> None:
        script = configure_trunk_port_js("SW1", "GigabitEthernet0/1")
        self.assertIn("setAdminOpMode(2)", script)
        self.assertIn("addTrunkVlans(1,4094)", script)
        self.assertIn("getAdminOpMode", script)

    def test_acl_configuration_uses_process_suffix(self) -> None:
        script = configure_acl_js(
            "R1", "10", ["deny host 192.168.10.10"], "GigabitEthernet0/1"
        )
        self.assertIn('getProcess("AclProcess")', script)
        self.assertIn("addStatement", script)
        self.assertIn("setAclOutID", script)

    def test_routing_state_reads_structured_properties(self) -> None:
        script = routing_state_js("R1")
        self.assertIn("routingNetworks", script)
        self.assertIn("staticRoutes", script)
        self.assertIn("adminDistance", script)

    def test_port_failure_uses_structured_power_control(self) -> None:
        script = set_port_power_js("R1", "GigabitEthernet0/1", False)
        self.assertIn("setPower(false)", script)
        self.assertIn("isPortUp", script)

    def test_rip_version_commands(self) -> None:
        commands = rip_config_commands(2, auto_summary=False)
        self.assertIn("version 2", commands)
        self.assertIn("no auto-summary", commands)


if __name__ == "__main__":
    unittest.main()
