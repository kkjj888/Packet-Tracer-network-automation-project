"""Topology builders for configuration integration tests."""

from __future__ import annotations

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
    return [
        "configure terminal",
        "vlan 10",
        "name FINANCE",
        "exit",
        "vlan 20",
        "name GUEST",
        "exit",
        "interface FastEthernet0/1",
        "switchport mode access",
        "switchport access vlan 10",
        "no shutdown",
        "exit",
        "interface FastEthernet0/2",
        "switchport mode access",
        "switchport access vlan 10",
        "no shutdown",
        "exit",
        "interface FastEthernet0/3",
        "switchport mode access",
        "switchport access vlan 20",
        "no shutdown",
        "exit",
        "end",
        "write memory",
        "show vlan brief",
    ]


def acl_router_config_commands() -> list[str]:
    return [
        "configure terminal",
        "interface GigabitEthernet0/0",
        "ip address 192.168.10.1 255.255.255.0",
        "no shutdown",
        "exit",
        "interface GigabitEthernet0/1",
        "ip address 192.168.20.1 255.255.255.0",
        "no shutdown",
        "exit",
        "end",
        "write memory",
        "show ip interface brief",
    ]


def acl_apply_commands() -> list[str]:
    return [
        "configure terminal",
        "access-list 10 deny host 192.168.10.10",
        "access-list 10 permit any",
        "interface GigabitEthernet0/1",
        "ip access-group 10 out",
        "exit",
        "end",
        "write memory",
        "show access-lists 10",
    ]


def show_vlan_commands() -> list[str]:
    return ["show vlan brief"]


def show_acl_commands() -> list[str]:
    return ["show access-lists 10"]


def trunk_switch_config_commands(access_vlans: dict[str, int]) -> list[str]:
    commands = [
        "configure terminal",
        "vlan 10",
        "name FINANCE",
        "exit",
        "vlan 20",
        "name GUEST",
        "exit",
    ]
    for port, vlan in access_vlans.items():
        commands.extend(
            [
                f"interface {port}",
                "switchport mode access",
                f"switchport access vlan {vlan}",
                "no shutdown",
                "exit",
            ]
        )
    commands.extend(
        [
            "interface GigabitEthernet0/1",
            "switchport mode trunk",
            "switchport trunk native vlan 1",
            "switchport trunk allowed vlan all",
            "no shutdown",
            "exit",
            "end",
            "write memory",
            "show interfaces trunk",
        ]
    )
    return commands


def rip_config_commands(
    version: int,
    *,
    auto_summary: bool = True,
    networks: tuple[str, ...] = ("172.16.0.0", "10.0.0.0"),
) -> list[str]:
    commands = [
        "configure terminal",
        "router rip",
        f"version {version}",
    ]
    if not auto_summary:
        commands.append("no auto-summary")
    else:
        commands.append("auto-summary")
    commands.extend(f"network {network}" for network in networks)
    commands.extend(["end", "write memory"])
    return commands


def ospf_config_commands(
    process_id: int = 100,
    *,
    networks: tuple[tuple[str, str, str], ...],
) -> list[str]:
    commands = ["configure terminal", f"router ospf {process_id}"]
    commands.extend(
        f"network {network} {wildcard} area {area}"
        for network, wildcard, area in networks
    )
    commands.extend(["end", "write memory"])
    return commands


def show_rip_config_commands() -> list[str]:
    return [
        "show running-config | include router rip|version|auto-summary|network"
    ]


def show_ospf_config_commands() -> list[str]:
    return [
        "show running-config | include router ospf| network |area"
    ]

