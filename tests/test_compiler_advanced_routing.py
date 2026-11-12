from __future__ import annotations

import unittest

from pt_agent.compiler.bgp import BgpConfig, BgpNeighbor, compile_bgp_config
from pt_agent.compiler.gre import GreTunnel, compile_gre_tunnel
from pt_agent.compiler.ospf import OspfNetwork, compile_ospf_config


class AdvancedRoutingCommandTests(unittest.TestCase):
    def test_compiles_multiarea_ospf_with_gre_interface(self) -> None:
        plan = compile_ospf_config(
            "ZX-R1",
            1,
            [
                OspfNetwork("10.22.4.0/27", 1),
                OspfNetwork("10.22.5.12/30", 0),
            ],
            router_id="10.22.5.10",
            passive_interfaces=("GigabitEthernet0/0.203",),
            point_to_point_interfaces=("Tunnel0",),
            area_ranges=((1, "10.22.4.0/25"),),
        )
        self.assertIn("router-id 10.22.5.10", plan.commands)
        self.assertIn("area 1 range 10.22.4.0 0.0.0.127", plan.commands)
        self.assertIn("passive-interface GigabitEthernet0/0.203", plan.commands)
        self.assertIn("interface Tunnel0", plan.commands)
        self.assertEqual(plan.safety_issues(), [])

    def test_compiles_gre_tunnel(self) -> None:
        plan = compile_gre_tunnel(
            "HQ-R1",
            [
                GreTunnel(
                    "Tunnel0",
                    "10.22.5.13/30",
                    "Serial0/0/0",
                    "10.22.5.10",
                )
            ],
        )
        self.assertIn("tunnel source Serial0/0/0", plan.commands)
        self.assertIn("tunnel destination 10.22.5.10", plan.commands)
        self.assertIn("ip address 10.22.5.13 255.255.255.252", plan.commands)
        self.assertEqual(plan.safety_issues(), [])

    def test_compiles_ebgp(self) -> None:
        plan = compile_bgp_config(
            "HQ-R1",
            BgpConfig(
                65302,
                router_id="10.22.0.199",
                neighbors=(BgpNeighbor("192.0.2.10", 65500),),
                networks=("192.0.2.144/29",),
            ),
        )
        self.assertIn("router bgp 65302", plan.commands)
        self.assertIn("neighbor 192.0.2.10 remote-as 65500", plan.commands)
        self.assertIn(
            "network 192.0.2.144 mask 255.255.255.248",
            plan.commands,
        )
        self.assertEqual(plan.safety_issues(), [])


if __name__ == "__main__":
    unittest.main()
