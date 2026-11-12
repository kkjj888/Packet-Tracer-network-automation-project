"""IPv4 routed-interface command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


@dataclass(frozen=True)
class RouterInterface:
    name: str
    address: str

    def rendered(self) -> tuple[str, str]:
        port = require_port(self.name, "interface name")
        try:
            interface = ipaddress.ip_interface(self.address)
        except ValueError as exc:
            raise CommandCompileError(
                f"invalid interface address {self.address!r}: {exc}"
            ) from exc
        if interface.version != 4:
            raise CommandCompileError("only IPv4 interface addresses are supported")
        if interface.network.prefixlen < 31 and interface.ip in (
            interface.network.network_address,
            interface.network.broadcast_address,
        ):
            raise CommandCompileError(
                f"{interface.ip} is not usable as an interface host address"
            )
        return port, f"{interface.ip} {interface.netmask}"


@dataclass(frozen=True)
class RouterSubinterface:
    parent_port: str
    name: str
    vlan_id: int
    address: str

    def rendered(self) -> tuple[str, str]:
        parent = require_port(self.parent_port, "parent interface")
        name = require_port(self.name, "subinterface name")
        if not name.startswith(f"{parent}."):
            raise CommandCompileError(
                f"subinterface {name} must be a child of {parent}"
            )
        if not isinstance(self.vlan_id, int) or not 1 <= self.vlan_id <= 4094:
            raise CommandCompileError("dot1Q VLAN must be an integer from 1 to 4094")
        _, address = RouterInterface(name, self.address).rendered()
        return parent, f"encapsulation dot1Q {self.vlan_id}|{name}|{address}"


def compile_vlan_subinterfaces(
    device: str,
    subinterfaces: Iterable[RouterSubinterface],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    parents: set[str] = set()
    children: set[str] = set()
    count = 0
    for subinterface in subinterfaces:
        parent, rendered = subinterface.rendered()
        encapsulation, name, address = rendered.split("|", 2)
        if name in children:
            raise CommandCompileError(f"subinterface {name} is duplicated")
        children.add(name)
        if parent not in parents:
            parents.add(parent)
            body.extend([f"interface {parent}", "no shutdown", "exit"])
        count += 1
        body.extend(
            [
                f"interface {name}",
                encapsulation,
                f"ip address {address}",
                "no shutdown",
                "exit",
            ]
        )
    if count == 0:
        raise CommandCompileError("at least one VLAN subinterface is required")
    shows = ["show ip interface brief"] if show else []
    return config_plan(
        device,
        "vlan-subinterfaces",
        body,
        show_commands=shows,
    )


def compile_ipv4_interfaces(
    device: str,
    interfaces: Iterable[RouterInterface],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[str] = set()
    count = 0
    for interface in interfaces:
        port, address = interface.rendered()
        if port in seen:
            raise CommandCompileError(f"interface {port} is duplicated")
        seen.add(port)
        count += 1
        body.extend(
            [
                f"interface {port}",
                f"ip address {address}",
                "no shutdown",
                "exit",
            ]
        )
    if count == 0:
        raise CommandCompileError("at least one interface is required")
    shows = ["show ip interface brief"] if show else []
    return config_plan(
        device,
        "interface-ipv4",
        body,
        show_commands=shows,
    )
