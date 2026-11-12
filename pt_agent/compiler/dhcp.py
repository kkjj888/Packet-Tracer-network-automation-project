"""IPv4 DHCP pool command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan


@dataclass(frozen=True)
class DhcpPool:
    name: str
    network: str
    default_router: str
    dns_servers: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()

    def rendered(self) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
        name = self.name.strip()
        if not name or any(char.isspace() for char in name):
            raise CommandCompileError("DHCP pool name must not contain whitespace")
        try:
            network = ipaddress.ip_network(self.network, strict=True)
            router = ipaddress.ip_address(self.default_router)
        except ValueError as exc:
            raise CommandCompileError(f"invalid DHCP pool: {exc}") from exc
        if network.version != 4 or router.version != 4:
            raise CommandCompileError("only IPv4 DHCP is supported")
        if router not in network:
            raise CommandCompileError(
                f"DHCP default router {router} is outside {network}"
            )
        dns = tuple(_ipv4(value, "DHCP DNS server") for value in self.dns_servers)
        excluded = tuple(_ipv4(value, "DHCP excluded address") for value in self.excluded)
        return name, str(network.network_address), str(network.netmask), dns, excluded


def compile_dhcp_config(
    device: str,
    pools: Iterable[DhcpPool],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    names: set[str] = set()
    count = 0
    for pool in pools:
        name, network, mask, dns, excluded = pool.rendered()
        if name.lower() in names:
            raise CommandCompileError(f"DHCP pool {name!r} is duplicated")
        names.add(name.lower())
        for address in excluded:
            body.append(f"ip dhcp excluded-address {address} {address}")
        body.append(f"ip dhcp pool {name}")
        body.append(f"network {network} {mask}")
        body.append(f"default-router {pool.default_router}")
        if dns:
            body.append(f"dns-server {' '.join(dns)}")
        body.append("exit")
        count += 1
    if count == 0:
        raise CommandCompileError("at least one DHCP pool is required")
    shows = ["show running-config | include ip dhcp"] if show else []
    return config_plan(device, "dhcp", body, show_commands=shows)


def _ipv4(value: str, field: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise CommandCompileError(f"invalid {field}: {value!r}") from exc
    if address.version != 4:
        raise CommandCompileError(f"{field} must be IPv4")
    return str(address)
