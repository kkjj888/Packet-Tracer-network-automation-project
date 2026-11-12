from __future__ import annotations

import unittest

from pt_agent.config_suite import (
    acl_apply_commands,
    acl_router_config_commands,
    ospf_config_commands,
    rip_config_commands,
    trunk_switch_config_commands,
    vlan_switch_config_commands,
)
from pt_agent.validation import CommandSafetyValidator


class ConfigSuiteCompilerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.safety = CommandSafetyValidator()

    def assert_safe(self, commands: list[str]) -> None:
        self.assertEqual(self.safety.validate(commands), [])

    def test_vlan_and_acl_suites_use_safe_templates(self) -> None:
        vlan = vlan_switch_config_commands()
        acl = acl_apply_commands()
        interfaces = acl_router_config_commands()
        self.assert_safe(vlan)
        self.assert_safe(acl)
        self.assert_safe(interfaces)
        self.assertIn("show vlan brief", vlan)
        self.assertIn("ip access-group 10 out", acl)
        self.assertIn("show ip interface brief", interfaces)

    def test_trunk_suite_combines_vlan_and_trunk_templates(self) -> None:
        commands = trunk_switch_config_commands(
            {
                "FastEthernet0/1": 10,
                "FastEthernet0/2": 20,
            }
        )
        self.assert_safe(commands)
        self.assertIn("switchport mode trunk", commands)
        self.assertIn("switchport access vlan 20", commands)
        self.assertIn("show interfaces trunk", commands)

    def test_routing_suites_use_safe_templates(self) -> None:
        rip = rip_config_commands(2, auto_summary=False)
        ospf = ospf_config_commands(
            100,
            networks=(
                ("172.16.10.0", "0.0.0.255", "0"),
                ("10.0.0.0", "0.0.0.3", "0"),
            ),
        )
        self.assert_safe(rip)
        self.assert_safe(ospf)
        self.assertIn("version 2", rip)
        self.assertIn("no auto-summary", rip)
        self.assertIn(
            "network 172.16.10.0 0.0.0.255 area 0",
            ospf,
        )


if __name__ == "__main__":
    unittest.main()
