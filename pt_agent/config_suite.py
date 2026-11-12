"""Topology builders for configuration integration tests."""

from __future__ import annotations

import ipaddress

from .compiler.acl import (
    AclBinding,
    AclDefinition,
    AclRule,
    compile_acl_config,
)
from .compiler.interface import (
    RouterInterface,
    compile_ipv4_interfaces,
)
from .compiler.ospf import OspfNetwork, compile_ospf_config
from .compiler.rip import RipConfig, compile_rip_config
from .compiler.trunk import TrunkPort, compile_trunk_config
from .compiler.vlan import (
    AccessPort,
    VlanDefinition,
    compile_vlan_config,
)
from .script_backend import LOGICAL_WORKSPACE


def vlan_topology_js() -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
  function add(type,model,name,x,y){{
    var assigned=lw.addDevice(type,model,x,y);
    if(!assigned)return null;
    var d=net.getDevice(assigned);
    d.setName(name);
    d.setPower(true);
    try{{d.skipBoot();}}catch(e){{}}
    return name;
  }}
  if(!add(8,"PC-PT","PC1",200,250))return "ERROR:pc1";
  if(!add(8,"PC-PT","PC2",200,500))return "ERROR:pc2";
  if(!add(8,"PC-PT","PC3",200,750))return "ERROR:pc3";
  if(!add(1,"2960-24TT","SW1",550,500))return "ERROR:sw1";
  var lwObject={LOGICAL_WORKSPACE};
  lwObject.createLink("PC1","FastEthernet0","SW1","FastEthernet0/1",8100);
  lwObject.createLink("PC2","FastEthernet0","SW1","FastEthernet0/2",8100);
  lwObject.createLink("PC3","FastEthernet0","SW1","FastEthernet0/3",8100);
  return JSON.stringify({{deviceCount:net.getDeviceCount(),linkCount:net.getLinkCount()}});
}})()"""


def acl_topology_js() -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
  function add(type,model,name,x,y){{
    var assigned=lw.addDevice(type,model,x,y);
    if(!assigned)return null;
    var d=net.getDevice(assigned);
    d.setName(name);
    d.setPower(true);
    try{{d.skipBoot();}}catch(e){{}}
    return name;
  }}
  if(!add(0,"2911","R1",500,450))return "ERROR:router";
  if(!add(8,"PC-PT","PC1",250,450))return "ERROR:pc1";
  if(!add(8,"PC-PT","PC2",750,450))return "ERROR:pc2";
  var lwObject={LOGICAL_WORKSPACE};
  lwObject.createLink("PC1","FastEthernet0","R1","GigabitEthernet0/0",8100);
  lwObject.createLink("PC2","FastEthernet0","R1","GigabitEthernet0/1",8100);
  return JSON.stringify({{deviceCount:net.getDeviceCount(),linkCount:net.getLinkCount()}});
}})()"""


def routed_two_router_topology_js() -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
  function add(type,model,name,x,y){{
    var assigned=lw.addDevice(type,model,x,y);
    if(!assigned)return null;
    var d=net.getDevice(assigned);
    d.setName(name);
    d.setPower(true);
    try{{d.skipBoot();}}catch(e){{}}
    return name;
  }}
  if(!add(0,"2911","R1",450,450))return "ERROR:r1";
  if(!add(0,"2911","R2",750,450))return "ERROR:r2";
  if(!add(8,"PC-PT","PC1",180,450))return "ERROR:pc1";
  if(!add(8,"PC-PT","PC2",1020,450))return "ERROR:pc2";
  var lwObject={LOGICAL_WORKSPACE};
  lwObject.createLink("PC1","FastEthernet0","R1","GigabitEthernet0/0",8100);
  lwObject.createLink("PC2","FastEthernet0","R2","GigabitEthernet0/0",8100);
  lwObject.createLink("R1","GigabitEthernet0/1","R2","GigabitEthernet0/1",8100);
  return JSON.stringify({{deviceCount:net.getDeviceCount(),linkCount:net.getLinkCount()}});
}})()"""


def trunk_topology_js() -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
  function add(type,model,name,x,y){{
    var assigned=lw.addDevice(type,model,x,y);
    if(!assigned)return null;
    var d=net.getDevice(assigned);
    d.setName(name);
    d.setPower(true);
    try{{d.skipBoot();}}catch(e){{}}
    return name;
  }}
  if(!add(1,"2960-24TT","SW1",430,450))return "ERROR:sw1";
  if(!add(1,"2960-24TT","SW2",730,450))return "ERROR:sw2";
  if(!add(8,"PC-PT","PC1",180,260))return "ERROR:pc1";
  if(!add(8,"PC-PT","PC2",980,260))return "ERROR:pc2";
  if(!add(8,"PC-PT","PC3",980,640))return "ERROR:pc3";
  var lwObject={LOGICAL_WORKSPACE};
  lwObject.createLink("PC1","FastEthernet0","SW1","FastEthernet0/1",8100);
  lwObject.createLink("SW1","GigabitEthernet0/1","SW2","GigabitEthernet0/1",8100);
  lwObject.createLink("PC2","FastEthernet0","SW2","FastEthernet0/1",8100);
  lwObject.createLink("PC3","FastEthernet0","SW2","FastEthernet0/2",8100);
  return JSON.stringify({{deviceCount:net.getDeviceCount(),linkCount:net.getLinkCount()}});
}})()"""


def vlan_switch_config_commands() -> list[str]:
    return compile_vlan_config(
        "SW1",
        [
            VlanDefinition(10, "FINANCE"),
            VlanDefinition(20, "GUEST"),
        ],
        [
            AccessPort("FastEthernet0/1", 10),
            AccessPort("FastEthernet0/2", 10),
            AccessPort("FastEthernet0/3", 20),
        ],
    ).as_list()


def acl_router_config_commands() -> list[str]:
    return compile_ipv4_interfaces(
        "R1",
        [
            RouterInterface("GigabitEthernet0/0", "192.168.10.1/24"),
            RouterInterface("GigabitEthernet0/1", "192.168.20.1/24"),
        ],
    ).as_list()


def acl_apply_commands() -> list[str]:
    return compile_acl_config(
        "R1",
        AclDefinition(
            "10",
            (
                AclRule("deny", "host", "192.168.10.10"),
                AclRule("permit", "any"),
            ),
        ),
        [AclBinding("GigabitEthernet0/1", "out")],
    ).as_list()


def show_vlan_commands() -> list[str]:
    return ["show vlan brief"]


def show_acl_commands() -> list[str]:
    return ["show access-lists 10"]


def trunk_switch_config_commands(access_vlans: dict[str, int]) -> list[str]:
    vlan_commands = compile_vlan_config(
        "SW1",
        [
            VlanDefinition(10, "FINANCE"),
            VlanDefinition(20, "GUEST"),
        ],
        [
            AccessPort(port, vlan)
            for port, vlan in access_vlans.items()
        ],
        show=False,
    ).as_list()
    trunk_commands = compile_trunk_config(
        "SW1",
        [TrunkPort("GigabitEthernet0/1")],
    ).as_list()
    return [*vlan_commands, *trunk_commands]


def rip_config_commands(
    version: int,
    *,
    auto_summary: bool = True,
    networks: tuple[str, ...] = ("172.16.0.0", "10.0.0.0"),
) -> list[str]:
    return compile_rip_config(
        "R1",
        RipConfig(version, networks, auto_summary=auto_summary),
    ).as_list()


def ospf_config_commands(
    process_id: int = 100,
    *,
    networks: tuple[tuple[str, str, str], ...],
) -> list[str]:
    converted: list[OspfNetwork] = []
    for network, wildcard, area in networks:
        wildcard_ip = ipaddress.IPv4Address(wildcard)
        mask = ipaddress.IPv4Address(int(wildcard_ip) ^ 0xFFFFFFFF)
        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
        converted.append(
            OspfNetwork(f"{network}/{prefix}", int(area))
        )
    return compile_ospf_config(
        "R1",
        process_id,
        converted,
    ).as_list()


def show_rip_config_commands() -> list[str]:
    return [
        "show running-config | include router rip|version|auto-summary|network"
    ]


def show_ospf_config_commands() -> list[str]:
    return [
        "show running-config | include router ospf| network |area"
    ]

