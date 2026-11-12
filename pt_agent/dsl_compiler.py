"""Compile validated network DSL into deterministic deployment plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .compiler.acl import (
    AclBinding,
    AclDefinition,
    AclRule,
    compile_acl_config,
)
from .compiler.base import CommandPlan
from .compiler.dhcp import DhcpPool, compile_dhcp_config
from .compiler.interface import (
    RouterInterface,
    RouterSubinterface,
    compile_ipv4_interfaces,
    compile_vlan_subinterfaces,
)
from .compiler.nat import PatConfig, compile_pat_config
from .compiler.ospf import OspfNetwork, compile_ospf_config
from .compiler.rip import RipConfig, compile_rip_config
from .compiler.static_routing import (
    StaticRoute,
    compile_static_routes,
)
from .compiler.trunk import TrunkPort, compile_trunk_config
from .compiler.vlan import (
    AccessPort,
    VlanDefinition,
    compile_vlan_config,
)
from .script_backend import LOGICAL_WORKSPACE
from .validation import NetworkValidator


class DslCompileError(ValueError):
    """A valid DSL document cannot be mapped to supported PT operations."""


DEVICE_TYPE_IDS = {
    "router": 0,
    "switch": 1,
    "pc": 8,
    "server": 9,
}


@dataclass(frozen=True)
class TopologyDevice:
    device_id: str
    device_type: str
    model: str
    x: int
    y: int


@dataclass(frozen=True)
class TopologyLink:
    from_endpoint: str
    to_endpoint: str
    cable: str


@dataclass(frozen=True)
class HostAddressConfig:
    device: str
    port: str
    address: str
    gateway: str | None


@dataclass(frozen=True)
class DhcpClientConfig:
    device: str
    port: str


@dataclass(frozen=True)
class LinkFailure:
    name: str
    device: str
    port: str


@dataclass(frozen=True)
class VerificationSpec:
    name: str
    source: str
    destination: str
    expected: str
    protocol: str


@dataclass(frozen=True)
class RouteAssertionSpec:
    device: str
    destination: str
    protocol: str
    next_hop: str | None
    interface: str | None
    admin_distance: int | None


@dataclass(frozen=True)
class TracerouteSpec:
    name: str
    source: str
    destination: str
    expected_hops: tuple[str, ...]


@dataclass(frozen=True)
class CompiledNetwork:
    project: str
    devices: tuple[TopologyDevice, ...]
    links: tuple[TopologyLink, ...]
    host_addresses: tuple[HostAddressConfig, ...]
    dhcp_clients: tuple[DhcpClientConfig, ...]
    link_failures: tuple[LinkFailure, ...]
    command_plans: tuple[CommandPlan, ...]
    verification: tuple[VerificationSpec, ...]
    route_assertions: tuple[RouteAssertionSpec, ...]
    traceroutes: tuple[TracerouteSpec, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "devices": [
                {
                    "id": device.device_id,
                    "type": device.device_type,
                    "model": device.model,
                }
                for device in self.devices
            ],
            "links": [
                {
                    "from": link.from_endpoint,
                    "to": link.to_endpoint,
                    "cable": link.cable,
                }
                for link in self.links
            ],
            "host_addresses": [
                {
                    "device": item.device,
                    "port": item.port,
                    "address": item.address,
                    "gateway": item.gateway,
                }
                for item in self.host_addresses
            ],
            "dhcp_clients": [
                {"device": item.device, "port": item.port}
                for item in self.dhcp_clients
            ],
            "link_failures": [
                {
                    "name": item.name,
                    "device": item.device,
                    "port": item.port,
                }
                for item in self.link_failures
            ],
            "command_plans": [
                {
                    "device": plan.device,
                    "module": plan.module,
                    "commands": list(plan.commands),
                }
                for plan in self.command_plans
            ],
            "verification": [
                {
                    "name": test.name,
                    "source": test.source,
                    "destination": test.destination,
                    "expected": test.expected,
                    "protocol": test.protocol,
                }
                for test in self.verification
            ],
            "route_assertions": [
                {
                    "device": item.device,
                    "destination": item.destination,
                    "protocol": item.protocol,
                    "next_hop": item.next_hop,
                    "interface": item.interface,
                    "admin_distance": item.admin_distance,
                }
                for item in self.route_assertions
            ],
            "traceroutes": [
                {
                    "name": item.name,
                    "source": item.source,
                    "destination": item.destination,
                    "expected_hops": list(item.expected_hops),
                }
                for item in self.traceroutes
            ],
        }


def compile_network_dsl(
    document: Mapping[str, object],
    *,
    validate: bool = True,
) -> CompiledNetwork:
    if validate:
        result = NetworkValidator().validate(document)
        if not result.valid:
            codes = ", ".join(
                sorted({issue.code for issue in result.issues if issue.severity == "error"})
            )
            raise DslCompileError(f"DSL validation failed: {codes}")

    devices = tuple(_compile_devices(document))
    device_types = {device.device_id: device.device_type for device in devices}
    links = tuple(_compile_links(document))
    host_addresses = tuple(_compile_host_addresses(document, device_types))
    dhcp_clients = tuple(_compile_dhcp_clients(document, device_types))
    link_failures = tuple(_compile_link_failures(document))
    plans = tuple(
        [
            *_compile_switch_plans(document, device_types),
            *_compile_router_plans(document, device_types),
            *_compile_dhcp_plans(document, device_types),
            *_compile_nat_plans(document, device_types),
            *_compile_acl_plans(document, device_types),
            *_compile_static_plans(document, device_types),
            *_compile_rip_plans(document, device_types),
            *_compile_ospf_plans(document, device_types),
        ]
    )
    return CompiledNetwork(
        project=str(document["project"]),
        devices=devices,
        links=links,
        host_addresses=host_addresses,
        dhcp_clients=dhcp_clients,
        link_failures=link_failures,
        command_plans=plans,
        verification=tuple(_compile_verification(document)),
        route_assertions=tuple(_compile_route_assertions(document)),
        traceroutes=tuple(_compile_traceroutes(document)),
    )


def _compile_devices(
    document: Mapping[str, object],
) -> list[TopologyDevice]:
    result: list[TopologyDevice] = []
    for index, item in enumerate(_as_list(document.get("devices"))):
        if not isinstance(item, dict):
            continue
        device_type = str(item["type"])
        if device_type not in DEVICE_TYPE_IDS:
            raise DslCompileError(
                f"unsupported device type for PT compilation: {device_type}"
            )
        column = index % 4
        row = index // 4
        result.append(
            TopologyDevice(
                str(item["id"]),
                device_type,
                str(item["model"]),
                160 + column * 260,
                180 + row * 240,
            )
        )
    return result


def _compile_links(document: Mapping[str, object]) -> list[TopologyLink]:
    result: list[TopologyLink] = []
    for item in _as_list(document.get("links")):
        if isinstance(item, dict):
            result.append(
                TopologyLink(
                    str(item["from"]),
                    str(item["to"]),
                    str(item.get("cable", "copper-straight")),
                )
            )
    return result


def _compile_host_addresses(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[HostAddressConfig]:
    result: list[HostAddressConfig] = []
    for item in _as_list(document.get("ipv4")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) not in ("pc", "server"):
            continue
        result.append(
            HostAddressConfig(
                device,
                str(item["port"]),
                str(item["address"]),
                str(item["gateway"]) if item.get("gateway") else None,
            )
        )
    return result


def _compile_dhcp_clients(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[DhcpClientConfig]:
    result: list[DhcpClientConfig] = []
    for item in _as_list(document.get("dhcp_clients")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) not in ("pc", "server"):
            raise DslCompileError(
                f"DHCP client {device} must be a PC or server"
            )
        result.append(DhcpClientConfig(device, str(item["port"])))
    return result


def _compile_link_failures(
    document: Mapping[str, object],
) -> list[LinkFailure]:
    return [
        LinkFailure(
            str(item["name"]),
            str(item["device"]),
            str(item["port"]),
        )
        for item in _as_list(document.get("link_failures"))
        if isinstance(item, dict)
    ]


def _compile_dhcp_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    dhcp = document.get("dhcp")
    if not isinstance(dhcp, dict):
        return []
    grouped: dict[str, list[DhcpPool]] = {}
    for item in _as_list(dhcp.get("pools")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(f"DHCP server {device} is not a router")
        grouped.setdefault(device, []).append(
            DhcpPool(
                str(item["name"]),
                str(item["network"]),
                str(item["default_router"]),
                tuple(str(value) for value in _as_list(item.get("dns_servers"))),
                tuple(str(value) for value in _as_list(item.get("excluded"))),
            )
        )
    return [
        compile_dhcp_config(device, pools)
        for device, pools in grouped.items()
    ]


def _compile_switch_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    switches = [
        device_id
        for device_id, device_type in device_types.items()
        if device_type == "switch"
    ]
    vlan_definitions = [
        VlanDefinition(int(item["id"]), str(item["name"]))
        for item in _as_list(document.get("vlans"))
        if isinstance(item, dict)
    ]
    assignments = [
        item
        for item in _as_list(document.get("vlan_assignments"))
        if isinstance(item, dict)
    ]
    plans: list[CommandPlan] = []
    for switch in switches:
        local = [
            item for item in assignments if str(item.get("device")) == switch
        ]
        if not local and not vlan_definitions:
            continue
        access_ports = [
            AccessPort(str(item["port"]), int(item["vlan"]))
            for item in local
            if item.get("mode") == "access"
        ]
        if vlan_definitions:
            plans.append(
                compile_vlan_config(
                    switch,
                    vlan_definitions,
                    access_ports,
                    show=False,
                )
            )
        trunk_ports = [
            TrunkPort(
                str(item["port"]),
                int(item.get("native_vlan", 1)),
                (
                    tuple(int(v) for v in item["allowed_vlans"])
                    if item.get("allowed_vlans")
                    else None
                ),
            )
            for item in local
            if item.get("mode") == "trunk"
        ]
        if trunk_ports:
            plans.append(compile_trunk_config(switch, trunk_ports))
    return plans


def _compile_router_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    grouped: dict[str, list[RouterInterface]] = {}
    subinterfaces: dict[str, list[RouterSubinterface]] = {}
    for item in _as_list(document.get("ipv4")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            continue
        if item.get("dot1q_vlan") is not None:
            subinterfaces.setdefault(device, []).append(
                RouterSubinterface(
                    str(item["parent_port"]),
                    str(item["port"]),
                    int(item["dot1q_vlan"]),
                    str(item["address"]),
                )
            )
        else:
            grouped.setdefault(device, []).append(
                RouterInterface(str(item["port"]), str(item["address"]))
            )
    plans = [
        compile_ipv4_interfaces(device, interfaces)
        for device, interfaces in grouped.items()
    ]
    plans.extend(
        compile_vlan_subinterfaces(device, items)
        for device, items in subinterfaces.items()
    )
    return plans


def _compile_nat_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    nat = document.get("nat")
    if not isinstance(nat, dict):
        return []
    grouped: dict[str, list[PatConfig]] = {}
    for item in _as_list(nat.get("pat")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(f"NAT device {device} is not a router")
        grouped.setdefault(device, []).append(
            PatConfig(
                str(item["acl_id"]),
                str(item["source_network"]),
                tuple(str(value) for value in _as_list(item["inside_interfaces"])),
                str(item["outside_interface"]),
            )
        )
    return [
        compile_pat_config(device, configs)
        for device, configs in grouped.items()
    ]


def _compile_acl_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    bindings = [
        item
        for item in _as_list(document.get("acl_bindings"))
        if isinstance(item, dict)
    ]
    plans: list[CommandPlan] = []
    for acl_item in _as_list(document.get("acls")):
        if not isinstance(acl_item, dict):
            continue
        acl_id = str(acl_item["id"])
        acl = AclDefinition(
            acl_id,
            tuple(
                AclRule(
                    str(rule["action"]),
                    str(rule["match"]),
                    str(rule["address"]) if rule.get("address") else None,
                    str(rule["wildcard"]) if rule.get("wildcard") else None,
                )
                for rule in _as_list(acl_item.get("rules"))
                if isinstance(rule, dict)
            ),
        )
        by_device: dict[str, list[AclBinding]] = {}
        for binding in bindings:
            if str(binding.get("acl")) != acl_id:
                continue
            device = str(binding["device"])
            if device_types.get(device) != "router":
                raise DslCompileError(
                    f"ACL {acl_id} is bound to non-router {device}"
                )
            by_device.setdefault(device, []).append(
                AclBinding(
                    str(binding["port"]),
                    str(binding["direction"]),
                )
            )
        for device, device_bindings in by_device.items():
            plans.append(compile_acl_config(device, acl, device_bindings))
    return plans


def _compile_static_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    routing = document.get("routing")
    if not isinstance(routing, dict):
        return []
    grouped: dict[str, list[StaticRoute]] = {}
    for item in _as_list(routing.get("static")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(f"static route device {device} is not a router")
        grouped.setdefault(device, []).append(
            StaticRoute(
                str(item["network"]),
                str(item["next_hop"]),
                int(item.get("admin_distance", 1)),
            )
        )
    return [
        compile_static_routes(device, routes)
        for device, routes in grouped.items()
    ]


def _compile_rip_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    routing = document.get("routing")
    if not isinstance(routing, dict) or not isinstance(routing.get("rip"), dict):
        return []
    rip = routing["rip"]
    config = RipConfig(
        int(rip["version"]),
        tuple(str(value) for value in _as_list(rip.get("networks"))),
        bool(rip.get("auto_summary", True)),
    )
    plans: list[CommandPlan] = []
    for device in _as_list(rip.get("devices")):
        device_id = str(device)
        if device_types.get(device_id) != "router":
            raise DslCompileError(f"RIP device {device_id} is not a router")
        plans.append(compile_rip_config(device_id, config))
    return plans


def _compile_ospf_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    routing = document.get("routing")
    if not isinstance(routing, dict) or not isinstance(routing.get("ospf"), dict):
        return []
    ospf = routing["ospf"]
    grouped: dict[str, list[OspfNetwork]] = {}
    for item in _as_list(ospf.get("networks")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(f"OSPF device {device} is not a router")
        grouped.setdefault(device, []).append(
            OspfNetwork(str(item["network"]), int(item["area"]))
        )
    plans: list[CommandPlan] = []
    for device in _as_list(ospf.get("devices")):
        device_id = str(device)
        networks = grouped.get(device_id, [])
        if not networks:
            raise DslCompileError(
                f"OSPF device {device_id} has no network statements"
            )
        plans.append(
            compile_ospf_config(
                device_id,
                int(ospf["process_id"]),
                networks,
            )
        )
    return plans


def _compile_verification(
    document: Mapping[str, object],
) -> list[VerificationSpec]:
    verification = document.get("verification")
    if not isinstance(verification, dict):
        return []
    return [
        VerificationSpec(
            str(item["name"]),
            str(item["source"]),
            str(item["destination"]),
            str(item["expected"]),
            str(item.get("protocol", "ping")),
        )
        for item in _as_list(verification.get("connectivity"))
        if isinstance(item, dict)
    ]


def _compile_route_assertions(
    document: Mapping[str, object],
) -> list[RouteAssertionSpec]:
    verification = document.get("verification")
    if not isinstance(verification, dict):
        return []
    return [
        RouteAssertionSpec(
            str(item["device"]),
            str(item["destination"]),
            str(item["protocol"]),
            str(item["next_hop"]) if item.get("next_hop") else None,
            str(item["interface"]) if item.get("interface") else None,
            int(item["admin_distance"]) if item.get("admin_distance") is not None else None,
        )
        for item in _as_list(verification.get("route_assertions"))
        if isinstance(item, dict)
    ]


def _compile_traceroutes(
    document: Mapping[str, object],
) -> list[TracerouteSpec]:
    verification = document.get("verification")
    if not isinstance(verification, dict):
        return []
    return [
        TracerouteSpec(
            str(item["name"]),
            str(item["source"]),
            str(item["destination"]),
            tuple(str(hop) for hop in _as_list(item.get("expected_hops"))),
        )
        for item in _as_list(verification.get("traceroute_tests"))
        if isinstance(item, dict)
    ]


def topology_js(network: CompiledNetwork) -> str:
    device_specs = [
        {
            "id": device.device_id,
            "type": DEVICE_TYPE_IDS[device.device_type],
            "model": device.model,
            "x": device.x,
            "y": device.y,
        }
        for device in network.devices
    ]
    link_specs = [
        {
            "from": link.from_endpoint,
            "to": link.to_endpoint,
            "cable": 8100,
        }
        for link in network.links
    ]
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
  var devices={_json(device_specs)};
  for(var i=0;i<devices.length;i++){{
    var spec=devices[i];
    var assigned=lw.addDevice(spec.type,spec.model,spec.x,spec.y);
    if(!assigned)return "ERROR:add_device:"+spec.id;
    var d=net.getDevice(assigned);
    d.setName(spec.id);
    d.setPower(true);
    try{{d.skipBoot();}}catch(e){{}}
  }}
  var links={_json(link_specs)};
  for(var j=0;j<links.length;j++){{
    var link=links[j];
    var left=link.from.split(":");
    var right=link.to.split(":");
    var created=lw.createLink(left[0],left[1],right[0],right[1],link.cable);
    if(!created)return "ERROR:create_link:"+link.from+"->"+link.to;
  }}
  return JSON.stringify({{
    deviceCount:net.getDeviceCount(),
    linkCount:net.getLinkCount()
  }});
}})()"""


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _json(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
