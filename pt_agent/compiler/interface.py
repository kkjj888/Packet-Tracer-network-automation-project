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
