"""eBGP command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan


@dataclass(frozen=True)
class BgpNeighbor:
    address: str
    remote_as: int

    def rendered(self) -> str:
        try:
            address = ipaddress.ip_address(self.address)
        except ValueError as exc:
            raise CommandCompileError(f"invalid BGP neighbor: {exc}") from exc
        if address.version != 4:
            raise CommandCompileError("only IPv4 BGP neighbors are supported")
        if not isinstance(self.remote_as, int) or not 1 <= self.remote_as <= 4294967295:
            raise CommandCompileError("BGP remote AS must be 1-4294967295")
        return f"neighbor {address} remote-as {self.remote_as}"


@dataclass(frozen=True)
class BgpConfig:
    local_as: int
    router_id: str | None = None
    neighbors: tuple[BgpNeighbor, ...] = ()
    networks: tuple[str, ...] = ()


def compile_bgp_config(
    device: str,
    config: BgpConfig,
    *,
    show: bool = True,
) -> CommandPlan:
    if not isinstance(config.local_as, int) or not 1 <= config.local_as <= 4294967295:
        raise CommandCompileError("BGP local AS must be 1-4294967295")
    body = [f"router bgp {config.local_as}", "bgp log-neighbor-changes", "no synchronization"]
    if config.router_id:
        try:
            router_id = ipaddress.ip_address(config.router_id)
        except ValueError as exc:
            raise CommandCompileError(f"invalid BGP router ID: {exc}") from exc
        if router_id.version != 4:
            raise CommandCompileError("BGP router ID must be IPv4")
        body.append(f"bgp router-id {router_id}")
    seen_neighbors: set[str] = set()
    for neighbor in config.neighbors:
        command = neighbor.rendered()
        address = command.split()[1]
        if address in seen_neighbors:
            raise CommandCompileError(f"BGP neighbor {address} is duplicated")
        seen_neighbors.add(address)
        body.append(command)
    seen_networks: set[str] = set()
    for value in config.networks:
        try:
            network = ipaddress.ip_network(value, strict=True)
        except ValueError as exc:
            raise CommandCompileError(f"invalid BGP network: {exc}") from exc
        if network.version != 4:
            raise CommandCompileError("only IPv4 BGP networks are supported")
        rendered = str(network)
        if rendered in seen_networks:
            raise CommandCompileError(f"BGP network {network} is duplicated")
        seen_networks.add(rendered)
        body.append(f"network {network.network_address} mask {network.netmask}")
    if not config.neighbors and not config.networks:
        raise CommandCompileError("BGP requires at least one neighbor or network")
    shows = ["show ip bgp summary"] if show else []
    return config_plan(device, "bgp", body, show_commands=shows)
