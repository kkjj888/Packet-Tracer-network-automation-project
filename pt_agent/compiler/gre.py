"""GRE tunnel command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


@dataclass(frozen=True)
class GreTunnel:
    interface: str
    address: str
    source: str
    destination: str
    mtu: int = 1476

    def rendered(self) -> list[str]:
        interface = require_port(self.interface, "tunnel interface")
        if not interface.lower().startswith("tunnel"):
            raise CommandCompileError("GRE interface name must start with Tunnel")
        try:
            address = ipaddress.ip_interface(self.address)
            destination = ipaddress.ip_address(self.destination)
        except ValueError as exc:
            raise CommandCompileError(f"invalid GRE tunnel: {exc}") from exc
        if address.version != 4 or destination.version != 4:
            raise CommandCompileError("only IPv4 GRE is supported")
        source = require_port(self.source, "tunnel source")
        if not isinstance(self.mtu, int) or not 576 <= self.mtu <= 1500:
            raise CommandCompileError("GRE MTU must be 576-1500")
        return [
            f"interface {interface}",
            f"ip address {address.ip} {address.netmask}",
            f"tunnel source {source}",
            f"tunnel destination {destination}",
            "no shutdown",
            "exit",
        ]


def compile_gre_tunnel(
    device: str,
    tunnels: Iterable[GreTunnel],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[str] = set()
    count = 0
    for tunnel in tunnels:
        name = tunnel.interface.lower()
        if name in seen:
            raise CommandCompileError(f"tunnel {tunnel.interface} is duplicated")
        seen.add(name)
        body.extend(tunnel.rendered())
        count += 1
    if not count:
        raise CommandCompileError("at least one GRE tunnel is required")
    shows = ["show interfaces tunnel 0"] if show else []
    return config_plan(device, "gre-tunnel", body, show_commands=shows)
