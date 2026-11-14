"""IPv6 interface, static-route, and GRE-over-IPv4 command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


@dataclass(frozen=True)
class Ipv6Interface:
    port: str
    address: str

    def rendered(self) -> tuple[str, str]:
        port = require_port(self.port)
        try:
            interface = ipaddress.ip_interface(self.address)
        except ValueError as exc:
            raise CommandCompileError(f"invalid IPv6 interface: {exc}") from exc
        if interface.version != 6:
            raise CommandCompileError("IPv6 interface requires an IPv6 prefix")
        return port, f"{interface.ip}/{interface.network.prefixlen}"


@dataclass(frozen=True)
class Ipv6StaticRoute:
    destination: str
    next_hop: str | None = None
    interface: str | None = None

    def rendered(self) -> str:
        try:
            network = ipaddress.ip_network(self.destination, strict=True)
        except ValueError as exc:
            raise CommandCompileError(f"invalid IPv6 static route: {exc}") from exc
        if network.version != 6:
            raise CommandCompileError("IPv6 static route requires an IPv6 prefix")
        if self.next_hop and self.interface:
            raise CommandCompileError(
                "IPv6 static route accepts next_hop or interface, not both"
            )
        if not self.next_hop and not self.interface:
            raise CommandCompileError("IPv6 static route requires a next hop")
        target = self.interface
        if self.next_hop:
            try:
                address = ipaddress.ip_address(self.next_hop)
            except ValueError as exc:
                raise CommandCompileError(
                    f"invalid IPv6 next hop: {exc}"
                ) from exc
            if address.version != 6:
                raise CommandCompileError("IPv6 next hop must be IPv6")
            target = str(address)
        return f"ipv6 route {network} {require_port(str(target), 'route target')}"


def compile_ipv6_config(
    device: str,
    interfaces: Iterable[Ipv6Interface],
    routes: Iterable[Ipv6StaticRoute] = (),
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = ["ipv6 unicast-routing"]
    seen: set[str] = set()
    interface_count = 0
    for item in interfaces:
        port, address = item.rendered()
        if port in seen:
            raise CommandCompileError(f"IPv6 interface {port} is duplicated")
        seen.add(port)
        body.extend(
            [
                f"interface {port}",
                f"ipv6 address {address}",
                "no shutdown",
                "exit",
            ]
        )
        interface_count += 1
    route_commands = [route.rendered() for route in routes]
    if interface_count == 0 and not route_commands:
        raise CommandCompileError("IPv6 configuration is empty")
    body.extend(route_commands)
    shows = ["show ipv6 interface brief"] if show else []
    return config_plan(device, "ipv6", body, show_commands=shows)


@dataclass(frozen=True)
class Ipv6GreTunnel:
    interface: str
    address: str
    source: str
    destination: str

    def rendered(self) -> list[str]:
        interface = require_port(self.interface, "tunnel interface")
        try:
            address = ipaddress.ip_interface(self.address)
            destination = ipaddress.ip_address(self.destination)
        except ValueError as exc:
            raise CommandCompileError(f"invalid IPv6 GRE tunnel: {exc}") from exc
        if address.version != 6 or destination.version != 4:
            raise CommandCompileError(
                "IPv6 GRE requires IPv6 tunnel address and IPv4 destination"
            )
        return [
            f"interface {interface}",
            "tunnel mode gre ip",
            f"tunnel source {require_port(self.source, 'tunnel source')}",
            f"tunnel destination {destination}",
            f"ipv6 address {address.ip}/{address.network.prefixlen}",
            "no shutdown",
            "exit",
        ]


def compile_ipv6_gre_tunnels(
    device: str,
    tunnels: Iterable[Ipv6GreTunnel],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[str] = set()
    count = 0
    for tunnel in tunnels:
        if tunnel.interface.lower() in seen:
            raise CommandCompileError(
                f"tunnel {tunnel.interface} is duplicated"
            )
        seen.add(tunnel.interface.lower())
        body.extend(tunnel.rendered())
        count += 1
    if count == 0:
        raise CommandCompileError("at least one IPv6 GRE tunnel is required")
    shows = ["show interfaces tunnel 0"] if show else []
    return config_plan(device, "ipv6-gre", body, show_commands=shows)
