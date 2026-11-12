from __future__ import annotations

import unittest

from pt_agent.compiler.platform import (
    HsrpGroup,
    RoutedSwitchPort,
    StpConfig,
    SviConfig,
    compile_hsrp_config,
    compile_management_config,
    compile_routed_switch_ports,
    compile_stp_config,
    compile_svi_config,
    compile_switch_routing,
)


class PlatformCommandTests(unittest.TestCase):
    def test_compiles_routed_ports_svis_and_switch_routing(self) -> None:
        routing = compile_switch_routing("CORE-A")
        port = compile_routed_switch_ports(
            "CORE-A",
            [RoutedSwitchPort("FastEthernet0/1", "10.22.5.1/30", True)],
        )
        svi = compile_svi_config(
            "CORE-A",
            [
                SviConfig(201, "10.22.0.156/27"),
                SviConfig(206, "10.22.0.124/26"),
            ],
        )
        self.assertIn("ip routing", routing.commands)
        self.assertIn("no switchport", port.commands)
        self.assertIn("ip ospf network point-to-point", port.commands)
        self.assertIn("interface Vlan201", svi.commands)
        self.assertIn("ip address 10.22.0.156 255.255.255.224", svi.commands)
        for plan in (routing, port, svi):
            self.assertEqual(plan.safety_issues(), [])

    def test_compiles_hsrp_and_stp(self) -> None:
        hsrp = compile_hsrp_config(
            "CORE-A",
            [
                HsrpGroup(
                    201,
                    201,
                    "10.22.0.158",
                    priority=110,
                    track_port="FastEthernet0/1",
                    track_decrement=20,
                )
            ],
        )
        stp = compile_stp_config(
            "CORE-A",
            [StpConfig("primary", (201, 202, 205, 206, 207, 208))],
        )
        self.assertIn("standby 201 ip 10.22.0.158", hsrp.commands)
        self.assertIn("standby 201 priority 110", hsrp.commands)
        self.assertIn("standby 201 preempt", hsrp.commands)
        self.assertIn(
            "standby 201 track FastEthernet0/1 20",
            hsrp.commands,
        )
        self.assertIn(
            "spanning-tree vlan 201-202,205-208 root primary",
            stp.commands,
        )
        self.assertEqual(hsrp.safety_issues(), [])
        self.assertEqual(stp.safety_issues(), [])

    def test_compiles_management_and_preserves_vty_acl(self) -> None:
        plan = compile_management_config(
            "HQ-R1",
            domain_name="akg.local",
            username="admin",
            password="Cisco123!",
            access_acl="99",
        )
        self.assertIn("username admin privilege 15 secret Cisco123!", plan.commands)
        self.assertIn("access-class 99 in", plan.commands)
        self.assertIn("transport input ssh", plan.commands)
        self.assertEqual(plan.safety_issues(), [])


if __name__ == "__main__":
    unittest.main()
