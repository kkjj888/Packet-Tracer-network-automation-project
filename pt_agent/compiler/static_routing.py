"""IPv4 static and default-route command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan


@dataclass(frozen=True)
class StaticRoute:
    destination: str
    next_hop: str
    admin_distance: int = 1

    def rendered(self) -> str:
        try:
            network = ipaddress.ip_network(self.destination, strict=True)
            next_hop = ipaddress.ip_address(self.next_hop)
        except ValueError as exc:
            raise CommandCompileError(f"invalid static route: {exc}") from exc
        if network.version != 4 or next_hop.version != 4:
            raise CommandCompileError("only IPv4 static routes are supported")
        if not isinstance(self.admin_distance, int) or not (
            1 <= self.admin_distance <= 255
        ):
            raise CommandCompileError(
                "static-route administrative distance must be 1-255"
            )
        command = (
            f"ip route {network.network_address} "
            f"{network.netmask} {next_hop}"
        )
        if self.admin_distance != 1:
            command += f" {self.admin_distance}"
        return command


def compile_static_routes(
    device: str,
    routes: Iterable[StaticRoute],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[tuple[str, str]] = set()
    count = 0
    for route in routes:
        command = route.rendered()
        network = ipaddress.ip_network(route.destination)
        identity = (str(network), str(ipaddress.ip_address(route.next_hop)))
        if identity in seen:
            raise CommandCompileError(
                f"static route {network} via {identity[1]} is duplicated"
            )
        seen.add(identity)
        count += 1
        body.append(command)
    if count == 0:
        raise CommandCompileError("at least one static route is required")
    shows = ["show ip route"] if show else []
    return config_plan(device, "static-routing", body, show_commands=shows)
