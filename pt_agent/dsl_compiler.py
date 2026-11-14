"""Compile validated network DSL into deterministic deployment plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .compiler.acl import (
    AclBinding,
    AclDefinition,
    AclEndpoint,
    AclRule,
    ExtendedAclRule,
    compile_acl_config,
)
from .compiler.base import CommandPlan
from .compiler.bgp import BgpConfig, BgpNeighbor, compile_bgp_config
from .compiler.dhcp import DhcpPool, compile_dhcp_config
from .compiler.gre import GreTunnel, compile_gre_tunnel
from .compiler.interface import (
    RouterInterface,
    RouterSubinterface,
    compile_ipv4_interfaces,
    compile_vlan_subinterfaces,
)
from .compiler.ipv6 import (
    Ipv6GreTunnel,
    Ipv6Interface,
    Ipv6StaticRoute,
    compile_ipv6_config,
    compile_ipv6_gre_tunnels,
)
from .compiler.nat import (
    PatConfig,
    StaticNatConfig,
    compile_pat_config,
    compile_static_nat_config,
)
from .compiler.ospf import OspfNetwork, compile_ospf_config
from .compiler.platform import (
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
    "access_point": 7,
    "pc": 8,
    "server": 9,
    "multilayer_switch": 16,
    "laptop": 18,
}

CABLE_TYPE_IDS = {
    "copper-straight": 8100,
    "copper-cross": 8101,
    "fiber": 8103,
    "console": 8108,
    "serial": 8106,
}

_HOST_TYPES = frozenset({"pc", "server", "laptop"})
_L2_TYPES = frozenset({"switch", "multilayer_switch"})
_L3_TYPES = frozenset({"router", "multilayer_switch"})


@dataclass(frozen=True)
class TopologyDevice:
    device_id: str
    device_type: str
    model: str
    x: int
    y: int
    modules: tuple[tuple[str, str], ...] = ()


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
class RouterInterfaceConfig:
    device: str
    interfaces: tuple[tuple[str, str], ...]


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
class WirelessConfig:
    access_point: str
    ssid: str
    clients: tuple[str, ...]
    encryption: str
    passphrase: str | None


@dataclass(frozen=True)
class OutputAssertionSpec:
    name: str
    device: str
    command: str
    expected_contains: tuple[str, ...]


@dataclass(frozen=True)
class CompiledNetwork:
    project: str
    devices: tuple[TopologyDevice, ...]
    links: tuple[TopologyLink, ...]
    host_addresses: tuple[HostAddressConfig, ...]
    host_ipv6_addresses: tuple[HostAddressConfig, ...]
    dhcp_clients: tuple[DhcpClientConfig, ...]
    dhcp_networks: tuple[str, ...]
    link_failures: tuple[LinkFailure, ...]
    command_plans: tuple[CommandPlan, ...]
    router_interfaces: tuple[RouterInterfaceConfig, ...]
    verification: tuple[VerificationSpec, ...]
    route_assertions: tuple[RouteAssertionSpec, ...]
    traceroutes: tuple[TracerouteSpec, ...]
    failure_verification: tuple[VerificationSpec, ...]
    failure_route_assertions: tuple[RouteAssertionSpec, ...]
    failure_traceroutes: tuple[TracerouteSpec, ...]
    wireless: WirelessConfig | None
    output_assertions: tuple[OutputAssertionSpec, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "devices": [
                {
                    "id": device.device_id,
                    "type": device.device_type,
                    "model": device.model,
                    "modules": [
                        {"name": name, "slot": slot}
                        for name, slot in device.modules
                    ],
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
            "host_ipv6_addresses": [
                {
                    "device": item.device,
                    "port": item.port,
                    "address": item.address,
                    "gateway": item.gateway,
                }
                for item in self.host_ipv6_addresses
            ],
            "dhcp_clients": [
                {"device": item.device, "port": item.port}
                for item in self.dhcp_clients
            ],
            "dhcp_networks": list(self.dhcp_networks),
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
            "router_interfaces": [
                {
                    "device": item.device,
                    "interfaces": [
                        {"port": port, "address": address}
                        for port, address in item.interfaces
                    ],
                }
                for item in self.router_interfaces
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
            "failure_verification": [
                {
                    "name": test.name,
                    "source": test.source,
                    "destination": test.destination,
                    "expected": test.expected,
                    "protocol": test.protocol,
                }
                for test in self.failure_verification
            ],
            "failure_route_assertions": [
                {
                    "device": item.device,
                    "destination": item.destination,
                    "protocol": item.protocol,
                    "next_hop": item.next_hop,
                    "interface": item.interface,
                    "admin_distance": item.admin_distance,
                }
                for item in self.failure_route_assertions
            ],
            "failure_traceroutes": [
                {
                    "name": item.name,
                    "source": item.source,
                    "destination": item.destination,
                    "expected_hops": list(item.expected_hops),
                }
                for item in self.failure_traceroutes
            ],
            "wireless": (
                {
                    "access_point": self.wireless.access_point,
                    "ssid": self.wireless.ssid,
                    "clients": list(self.wireless.clients),
                    "encryption": self.wireless.encryption,
                }
                if self.wireless
                else None
            ),
            "output_assertions": [
                {
                    "name": item.name,
                    "device": item.device,
                    "command": item.command,
                    "expected_contains": list(item.expected_contains),
                }
                for item in self.output_assertions
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
    host_ipv6_addresses = tuple(
        _compile_host_ipv6_addresses(document, device_types)
    )
    router_interfaces = tuple(
        _compile_router_interface_configs(document, device_types)
    )
    dhcp_clients = tuple(_compile_dhcp_clients(document, device_types))
    link_failures = tuple(_compile_link_failures(document))
    plans = tuple(
        [
            *_compile_switch_plans(document, device_types),
            *_compile_platform_plans(document, device_types),
            *_compile_router_plans(document, device_types),
            *_compile_static_plans(document, device_types),
            *_compile_tunnel_plans(document, device_types),
            *_compile_ipv6_plans(document, device_types),
            *_compile_dhcp_plans(document, device_types),
            *_compile_nat_plans(document, device_types),
            *_compile_static_nat_plans(document, device_types),
            *_compile_acl_plans(document, device_types),
            *_compile_rip_plans(document, device_types),
            *_compile_ospf_plans(document, device_types),
            *_compile_bgp_plans(document, device_types),
            *_compile_management_plans(document, device_types),
        ]
    )
    verification = document.get("verification")
    after_failure = (
        verification.get("after_failure")
        if isinstance(verification, dict)
        else None
    )
    failure_document = (
        {"verification": after_failure}
        if isinstance(after_failure, dict)
        else {}
    )
    return CompiledNetwork(
        project=str(document["project"]),
        devices=devices,
        links=links,
        host_addresses=host_addresses,
        host_ipv6_addresses=host_ipv6_addresses,
        dhcp_clients=dhcp_clients,
        dhcp_networks=tuple(_compile_dhcp_networks(document)),
        link_failures=link_failures,
        command_plans=plans,
        router_interfaces=router_interfaces,
        verification=tuple(_compile_verification(document)),
        route_assertions=tuple(_compile_route_assertions(document)),
        traceroutes=tuple(_compile_traceroutes(document)),
        failure_verification=tuple(_compile_verification(failure_document)),
        failure_route_assertions=tuple(
            _compile_route_assertions(failure_document)
        ),
        failure_traceroutes=tuple(
            _compile_traceroutes(failure_document)
        ),
        wireless=_compile_wireless(document, device_types),
        output_assertions=tuple(_compile_output_assertions(document)),
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
        modules = tuple(
            (str(module["name"]), str(module["slot"]))
            for module in _as_list(item.get("modules"))
            if isinstance(module, dict)
        )
        result.append(
            TopologyDevice(
                str(item["id"]),
                device_type,
                str(item["model"]),
                int(item.get("x", 160 + column * 260)),
                int(item.get("y", 180 + row * 240)),
                modules,
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
        if device_types.get(device) not in _HOST_TYPES:
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


def _compile_host_ipv6_addresses(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[HostAddressConfig]:
    result: list[HostAddressConfig] = []
    for item in _as_list(document.get("ipv6")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) not in _HOST_TYPES:
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


def _compile_router_interface_configs(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[RouterInterfaceConfig]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for item in _as_list(document.get("ipv4")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            continue
        if item.get("dot1q_vlan") is not None:
            continue
        grouped.setdefault(device, []).append(
            (str(item["port"]), str(item["address"]))
        )
    return [
        RouterInterfaceConfig(device, tuple(interfaces))
        for device, interfaces in grouped.items()
    ]


def _compile_dhcp_clients(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[DhcpClientConfig]:
    result: list[DhcpClientConfig] = []
    for item in _as_list(document.get("dhcp_clients")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) not in _HOST_TYPES:
            raise DslCompileError(
                f"DHCP client {device} must be a PC, server, or laptop"
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
        if device_types.get(device) not in _L3_TYPES:
            raise DslCompileError(
                f"DHCP server {device} is not a layer-3 device"
            )
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


def _compile_dhcp_networks(document: Mapping[str, object]) -> list[str]:
    dhcp = document.get("dhcp")
    if not isinstance(dhcp, dict):
        return []
    return [
        str(item["network"])
        for item in _as_list(dhcp.get("pools"))
        if isinstance(item, dict)
    ]


def _compile_switch_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    switches = [
        device_id
        for device_id, device_type in device_types.items()
        if device_type in _L2_TYPES
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
                True,
            )
            for item in local
            if item.get("mode") == "trunk"
        ]
        if trunk_ports:
            plans.append(
                compile_trunk_config(
                    switch,
                    trunk_ports,
                    dot1q_encapsulation=(
                        device_types.get(switch) == "multilayer_switch"
                    ),
                )
            )
    return plans


def _compile_platform_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    plans: list[CommandPlan] = []
    for device in _as_list(document.get("switch_routing")):
        device_id = str(device)
        if device_types.get(device_id) != "multilayer_switch":
            raise DslCompileError(
                f"switch routing device {device_id} is not a multilayer switch"
            )
        plans.append(compile_switch_routing(device_id))

    routed_ports: dict[str, list[RoutedSwitchPort]] = {}
    for item in _as_list(document.get("ipv4")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "multilayer_switch":
            continue
        routed_ports.setdefault(device, []).append(
            RoutedSwitchPort(
                str(item["port"]),
                str(item["address"]),
                point_to_point=bool(item.get("point_to_point", False)),
            )
        )
    plans.extend(
        compile_routed_switch_ports(device, ports)
        for device, ports in routed_ports.items()
    )

    svis: dict[str, list[SviConfig]] = {}
    for item in _as_list(document.get("svis")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) not in _L2_TYPES:
            raise DslCompileError(f"SVI device {device} is not a switch")
        svis.setdefault(device, []).append(
            SviConfig(int(item["vlan"]), str(item["address"]))
        )
    plans.extend(
        compile_svi_config(device, items) for device, items in svis.items()
    )

    hsrp: dict[str, list[HsrpGroup]] = {}
    for item in _as_list(document.get("hsrp")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "multilayer_switch":
            raise DslCompileError(f"HSRP device {device} is not a multilayer switch")
        hsrp.setdefault(device, []).append(
            HsrpGroup(
                int(item["vlan"]),
                int(item["group"]),
                str(item["virtual_ip"]),
                int(item.get("priority", 100)),
                bool(item.get("preempt", True)),
                str(item["track_port"]) if item.get("track_port") else None,
                (
                    int(item["track_decrement"])
                    if item.get("track_decrement") is not None
                    else None
                ),
            )
        )
    plans.extend(
        compile_hsrp_config(device, items) for device, items in hsrp.items()
    )

    stp: dict[str, list[StpConfig]] = {}
    for item in _as_list(document.get("stp")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "multilayer_switch":
            raise DslCompileError(f"STP device {device} is not a multilayer switch")
        stp.setdefault(device, []).append(
            StpConfig(
                str(item["role"]),
                tuple(int(vlan) for vlan in _as_list(item["vlans"])),
                int(item["priority"]) if item.get("priority") is not None else None,
            )
        )
    plans.extend(
        compile_stp_config(device, items) for device, items in stp.items()
    )
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


def _compile_ipv6_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    interfaces: dict[str, list[Ipv6Interface]] = {}
    for item in _as_list(document.get("ipv6")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            continue
        interfaces.setdefault(device, []).append(
            Ipv6Interface(str(item["port"]), str(item["address"]))
        )

    routes: dict[str, list[Ipv6StaticRoute]] = {}
    routing = document.get("routing")
    if isinstance(routing, dict):
        for item in _as_list(routing.get("ipv6_static")):
            if not isinstance(item, dict):
                continue
            device = str(item["device"])
            if device_types.get(device) != "router":
                raise DslCompileError(
                    f"IPv6 static route device {device} is not a router"
                )
            routes.setdefault(device, []).append(
                Ipv6StaticRoute(
                    str(item["destination"]),
                    (
                        str(item["next_hop"])
                        if item.get("next_hop")
                        else None
                    ),
                    (
                        str(item["interface"])
                        if item.get("interface")
                        else None
                    ),
                )
            )

    tunnels: dict[str, list[Ipv6GreTunnel]] = {}
    for item in _as_list(document.get("ipv6_tunnels")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(
                f"IPv6 GRE device {device} is not a router"
            )
        tunnels.setdefault(device, []).append(
            Ipv6GreTunnel(
                str(item["interface"]),
                str(item["address"]),
                str(item["source"]),
                str(item["destination"]),
            )
        )
    plans: list[CommandPlan] = [
        compile_ipv6_gre_tunnels(device, items)
        for device, items in tunnels.items()
    ]
    plans.extend(
        compile_ipv6_config(
            device,
            interfaces.get(device, []),
            routes.get(device, []),
        )
        for device in sorted(set(interfaces) | set(routes))
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
        if device_types.get(device) not in _L3_TYPES:
            raise DslCompileError(f"NAT device {device} is not a layer-3 device")
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


def _compile_static_nat_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    nat = document.get("nat")
    if not isinstance(nat, dict):
        return []
    grouped: dict[str, list[StaticNatConfig]] = {}
    for item in _as_list(nat.get("static")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) not in _L3_TYPES:
            raise DslCompileError(
                f"static NAT device {device} is not a layer-3 device"
            )
        grouped.setdefault(device, []).append(
            StaticNatConfig(
                str(item["protocol"]),
                str(item["inside_address"]),
                int(item["inside_port"]),
                str(item["outside_address"]),
                int(item["outside_port"]),
                tuple(
                    str(value) for value in _as_list(item["inside_interfaces"])
                ),
                str(item["outside_interface"]),
            )
        )
    return [
        compile_static_nat_config(device, configs)
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
        kind = str(acl_item.get("kind", "standard"))
        acl = AclDefinition(
            acl_id,
            tuple(
                (
                    ExtendedAclRule(
                        str(rule["action"]),
                        str(rule["protocol"]),
                        _compile_acl_endpoint(rule["source"]),
                        _compile_acl_endpoint(rule["destination"]),
                        rule.get("destination_port_eq"),
                        (
                            str(rule["icmp_type"])
                            if rule.get("icmp_type")
                            else None
                        ),
                        bool(rule.get("established", False)),
                    )
                    if kind == "extended"
                    else AclRule(
                        str(rule["action"]),
                        str(rule["match"]),
                        (
                            str(rule["address"])
                            if rule.get("address")
                            else None
                        ),
                        (
                            str(rule["wildcard"])
                            if rule.get("wildcard")
                            else None
                        ),
                    )
                )
                for rule in _as_list(acl_item.get("rules"))
                if isinstance(rule, dict)
            ),
            kind,
        )
        by_device: dict[str, list[AclBinding]] = {}
        for binding in bindings:
            if str(binding.get("acl")) != acl_id:
                continue
            device = str(binding["device"])
            if device_types.get(device) not in _L3_TYPES:
                raise DslCompileError(
                    f"ACL {acl_id} is bound to non-layer-3 device {device}"
                )
            by_device.setdefault(device, []).append(
                AclBinding(
                    str(binding["port"]),
                    str(binding["direction"]),
                )
            )
        management = document.get("management")
        management_access_acl = (
            str(management.get("access_acl"))
            if isinstance(management, dict)
            and management.get("access_acl") is not None
            else None
        )
        if management_access_acl == acl_id:
            for device in _as_list(management.get("devices")):
                device_id = str(device)
                if device_id not in by_device:
                    by_device[device_id] = []
        for device, device_bindings in by_device.items():
            plans.append(
                compile_acl_config(
                    device,
                    acl,
                    device_bindings,
                    require_binding=bool(device_bindings),
                )
            )
    return plans


def _compile_acl_endpoint(value: object) -> AclEndpoint:
    if not isinstance(value, dict):
        raise DslCompileError("extended ACL endpoint must be a mapping")
    return AclEndpoint(
        str(value["kind"]),
        str(value["address"]) if value.get("address") else None,
        str(value["wildcard"]) if value.get("wildcard") else None,
    )


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
        if device_types.get(device) not in _L3_TYPES:
            raise DslCompileError(
                f"static route device {device} is not a layer-3 device"
            )
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


def _compile_tunnel_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    routing = document.get("routing")
    if not isinstance(routing, dict):
        return []
    grouped: dict[str, list[GreTunnel]] = {}
    for item in _as_list(routing.get("tunnels")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(f"GRE device {device} is not a router")
        grouped.setdefault(device, []).append(
            GreTunnel(
                str(item["interface"]),
                str(item["address"]),
                str(item["source"]),
                str(item["destination"]),
                int(item.get("mtu", 1476)),
            )
        )
    return [
        compile_gre_tunnel(device, tunnels)
        for device, tunnels in grouped.items()
    ]


def _compile_bgp_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    routing = document.get("routing")
    if not isinstance(routing, dict) or not isinstance(routing.get("bgp"), dict):
        return []
    plans: list[CommandPlan] = []
    for item in _as_list(routing["bgp"].get("devices")):
        if not isinstance(item, dict):
            continue
        device = str(item["device"])
        if device_types.get(device) != "router":
            raise DslCompileError(f"BGP device {device} is not a router")
        plans.append(
            compile_bgp_config(
                device,
                BgpConfig(
                    int(item["local_as"]),
                    (
                        str(item["router_id"])
                        if item.get("router_id")
                        else None
                    ),
                    tuple(
                        BgpNeighbor(
                            str(neighbor["address"]),
                            int(neighbor["remote_as"]),
                        )
                        for neighbor in _as_list(item.get("neighbors"))
                        if isinstance(neighbor, dict)
                    ),
                    tuple(
                        str(network)
                        for network in _as_list(item.get("networks"))
                    ),
                ),
            )
        )
    return plans


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
        if device_types.get(device_id) not in _L3_TYPES:
            raise DslCompileError(
                f"RIP device {device_id} is not a layer-3 device"
            )
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
        if device_types.get(device) not in _L3_TYPES:
            raise DslCompileError(
                f"OSPF device {device} is not a layer-3 device"
            )
        grouped.setdefault(device, []).append(
            OspfNetwork(str(item["network"]), int(item["area"]))
        )
    settings = {
        str(item["device"]): item
        for item in _as_list(ospf.get("settings"))
        if isinstance(item, dict) and item.get("device")
    }
    area_ranges: dict[str, list[tuple[int, str]]] = {}
    for item in _as_list(ospf.get("area_ranges")):
        if not isinstance(item, dict):
            continue
        area_ranges.setdefault(str(item["device"]), []).append(
            (int(item["area"]), str(item["network"]))
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
                router_id=(
                    str(settings.get(device_id, {}).get("router_id"))
                    if settings.get(device_id, {}).get("router_id")
                    else (
                        str(ospf["router_id"])
                        if ospf.get("router_id")
                        else None
                    )
                ),
                passive_interfaces=tuple(
                    str(value)
                    for value in _as_list(
                        settings.get(device_id, {}).get("passive_interfaces")
                    )
                ),
                point_to_point_interfaces=tuple(
                    str(value)
                    for value in _as_list(
                        settings.get(device_id, {}).get(
                            "point_to_point_interfaces"
                        )
                    )
                ),
                default_information_originate=bool(
                    settings.get(device_id, {}).get(
                        "default_information_originate",
                        ospf.get("default_information_originate", False),
                    )
                ),
                area_ranges=tuple(area_ranges.get(device_id, [])),
            )
        )
    return plans


def _compile_management_plans(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> list[CommandPlan]:
    management = document.get("management")
    if not isinstance(management, dict):
        return []
    domain_name = str(management.get("domain_name", "bonus.local"))
    username = str(management.get("username", "admin"))
    password = str(management.get("password", "Cisco123!"))
    access_acl = (
        str(management["access_acl"])
        if management.get("access_acl") is not None
        else None
    )
    plans: list[CommandPlan] = []
    for device in _as_list(management.get("devices")):
        device_id = str(device)
        if device_types.get(device_id) not in _L3_TYPES:
            raise DslCompileError(
                f"management device {device_id} is not a layer-3 device"
            )
        plans.append(
            compile_management_config(
                device_id,
                domain_name=domain_name,
                username=username,
                password=password,
                access_acl=access_acl,
            )
        )
    return plans


def _compile_wireless(
    document: Mapping[str, object],
    device_types: Mapping[str, str],
) -> WirelessConfig | None:
    wireless = document.get("wireless")
    if not isinstance(wireless, dict):
        return None
    access_point = str(wireless["access_point"])
    if device_types.get(access_point) != "access_point":
        raise DslCompileError(
            f"wireless access point {access_point} has the wrong device type"
        )
    clients = tuple(str(value) for value in _as_list(wireless["clients"]))
    for client in clients:
        if device_types.get(client) != "laptop":
            raise DslCompileError(
                f"wireless client {client} is not a laptop"
            )
    encryption = str(wireless.get("encryption", "open"))
    passphrase = (
        str(wireless["passphrase"])
        if wireless.get("passphrase") is not None
        else None
    )
    return WirelessConfig(
        access_point,
        str(wireless["ssid"]),
        clients,
        encryption,
        passphrase,
    )


def _compile_verification(
    document: Mapping[str, object],
) -> list[VerificationSpec]:
    verification = document.get("verification")
    if not isinstance(verification, dict):
        return []
    result = [
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
    for matrix in _as_list(verification.get("connectivity_matrix")):
        if not isinstance(matrix, dict):
            continue
        name = str(matrix["name"])
        devices = [str(value) for value in _as_list(matrix["devices"])]
        protocol = str(matrix.get("protocol", "ping"))
        expected = str(matrix["expected"])
        for source in devices:
            for target in devices:
                if source == target:
                    continue
                result.append(
                    VerificationSpec(
                        f"{name}__{source}__to__{target}",
                        source,
                        target,
                        expected,
                        protocol,
                    )
                )
    return result


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


def _compile_output_assertions(
    document: Mapping[str, object],
) -> list[OutputAssertionSpec]:
    verification = document.get("verification")
    if not isinstance(verification, dict):
        return []
    return [
        OutputAssertionSpec(
            str(item["name"]),
            str(item["device"]),
            str(item["command"]),
            tuple(str(value) for value in _as_list(item["expected_contains"])),
        )
        for item in _as_list(verification.get("device_output_assertions"))
        if isinstance(item, dict)
    ]


def _topology_device_specs(network: CompiledNetwork) -> list[dict[str, object]]:
    wireless_clients = (
        set(network.wireless.clients) if network.wireless else set()
    )
    return [
        {
            "id": device.device_id,
            "type": DEVICE_TYPE_IDS[device.device_type],
            "model": device.model,
            "x": device.x,
            "y": device.y,
            "modules": [
                {"name": name, "slot": slot}
                for name, slot in device.modules
            ],
            "wireless": device.device_id in wireless_clients,
        }
        for device in network.devices
    ]


def _topology_link_specs(network: CompiledNetwork) -> list[dict[str, object]]:
    return [
        {
            "from": link.from_endpoint,
            "to": link.to_endpoint,
            "cable": CABLE_TYPE_IDS.get(link.cable, 8100),
        }
        for link in network.links
    ]


def _device_creation_js(network: CompiledNetwork) -> str:
    return f"""  var devices={_json(_topology_device_specs(network))};
  for(var i=0;i<devices.length;i++){{
    var spec=devices[i];
    var assigned=lw.addDevice(spec.type,spec.model,spec.x,spec.y);
    if(!assigned)return "ERROR:add_device:"+spec.id;
    var d=net.getDevice(assigned);
    d.setName(spec.id);
    d.setPower(true);
    try{{d.skipBoot();}}catch(e){{}}
    if(spec.wireless){{
      var wireless=false;
      for(var wp=0;wp<d.getPortCount();wp++){{
        var wpPort=d.getPortAt(wp);
        if(wpPort&&typeof wpPort.isWirelessPort==="function"&&wpPort.isWirelessPort()){{
          wireless=true;
          break;
        }}
      }}
      if(!wireless){{
        var root=d.getRootModule();
        var slotType=Number(root.getSlotTypeAt(0));
        d.setPower(false);
        root.removeModuleAt(0);
        d.addModule("0",slotType,"PT-LAPTOP-NM-1W");
        d.setPower(true);
        try{{d.skipBoot();}}catch(e){{}}
      }}
    }}
    for(var mi=0;mi<spec.modules.length;mi++){{
      var mod=spec.modules[mi];
      var parts=String(mod.slot).split("/");
      var idx=[];
      for(var px=0;px<parts.length;px++)idx.push(parseInt(parts[px],10));
      var parent=d.getRootModule();
      for(var di=0;di<idx.length-1;di++)parent=parent.getModuleAt(idx[di]);
      var wasOn=false;
      try{{wasOn=!!d.getPower();}}catch(e){{}}
      try{{if(wasOn)d.setPower(false);}}catch(e){{}}
      var moduleAdded=parent.addModuleAt(mod.name,idx[idx.length-1]);
      try{{if(wasOn)d.setPower(true);d.skipBoot();}}catch(e){{}}
      if(!moduleAdded)return "ERROR:add_module:"+spec.id+":"+mod.name;
    }}
  }}
"""


def _link_creation_js(network: CompiledNetwork) -> str:
    return f"""  var links={_json(_topology_link_specs(network))};
  for(var j=0;j<links.length;j++){{
    var link=links[j];
    var left=link.from.split(":");
    var right=link.to.split(":");
    var created=lw.createLink(left[0],left[1],right[0],right[1],link.cable);
    if(!created)return "ERROR:create_link:"+link.from+"->"+link.to;
  }}
"""


def topology_devices_js(network: CompiledNetwork) -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
{_device_creation_js(network)}
  return JSON.stringify({{deviceCount:net.getDeviceCount()}});
}})()"""


def topology_links_js(network: CompiledNetwork) -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
{_link_creation_js(network)}
  return JSON.stringify({{linkCount:net.getLinkCount()}});
}})()"""


def topology_js(network: CompiledNetwork) -> str:
    return f"""(function(){{
  var lw={LOGICAL_WORKSPACE};
  var net=ipc.network();
{_device_creation_js(network)}
{_link_creation_js(network)}
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
