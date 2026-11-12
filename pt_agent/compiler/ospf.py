"""OSPFv2 command templates with deterministic wildcard masks."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan


@dataclass(frozen=True)
class OspfNetwork:
    network: str
    area: int

    def rendered(self) -> str:
        try:
            parsed = ipaddress.ip_network(self.network, strict=True)
        except ValueError as exc:
            raise CommandCompileError(f"invalid OSPF network: {exc}") from exc
        if parsed.version != 4:
            raise CommandCompileError("only OSPFv2 IPv4 networks are supported")
        if not isinstance(self.area, int) or not 0 <= self.area <= 0xFFFFFFFF:
            raise CommandCompileError(
                "OSPF area must be an integer from 0 to 4294967295"
            )
        wildcard = ipaddress.IPv4Address(
            int(parsed.netmask) ^ 0xFFFFFFFF
        )
        return f"{parsed.network_address} {wildcard} area {self.area}"


def wildcard_mask(prefix: str) -> str:
    try:
        network = ipaddress.ip_network(prefix, strict=True)
    except ValueError as exc:
        raise CommandCompileError(f"invalid network prefix: {exc}") from exc
    if network.version != 4:
        raise CommandCompileError("wildcard_mask only supports IPv4")
    return str(ipaddress.IPv4Address(int(network.netmask) ^ 0xFFFFFFFF))


def compile_ospf_config(
    device: str,
    process_id: int,
    networks: Iterable[OspfNetwork],
    *,
    router_id: str | None = None,
    passive_interfaces: tuple[str, ...] = (),
    point_to_point_interfaces: tuple[str, ...] = (),
    default_information_originate: bool = False,
    area_ranges: tuple[tuple[int, str], ...] = (),
    show: bool = True,
) -> CommandPlan:
    if not isinstance(process_id, int) or not 1 <= process_id <= 65535:
        raise CommandCompileError("OSPF process ID must be 1-65535")
    body = [f"router ospf {process_id}"]
    if router_id:
        try:
            parsed_router_id = ipaddress.ip_address(router_id)
        except ValueError as exc:
            raise CommandCompileError(f"invalid OSPF router ID: {exc}") from exc
        if parsed_router_id.version != 4:
            raise CommandCompileError("OSPF router ID must be IPv4")
        body.append(f"router-id {parsed_router_id}")
    body.append("log-adjacency-changes")
    for interface in point_to_point_interfaces:
        body.extend(
            [
                f"interface {interface}",
                "ip ospf network point-to-point",
                "exit",
            ]
        )
    seen_ranges: set[tuple[int, str]] = set()
    for area, prefix in area_ranges:
        try:
            network = ipaddress.ip_network(prefix, strict=True)
        except ValueError as exc:
            raise CommandCompileError(f"invalid OSPF area range: {exc}") from exc
        wildcard = ipaddress.IPv4Address(int(network.netmask) ^ 0xFFFFFFFF)
        identity = (int(area), str(network))
        if identity in seen_ranges:
            raise CommandCompileError(
                f"OSPF area {area} range {network} is duplicated"
            )
        seen_ranges.add(identity)
        body.append(
            f"area {area} range {network.network_address} {wildcard}"
        )
    for interface in passive_interfaces:
        body.append(f"passive-interface {interface}")
    seen: set[tuple[str, int]] = set()
    count = 0
    for network in networks:
        rendered = network.rendered()
        parsed = ipaddress.ip_network(network.network, strict=True)
        identity = (str(parsed), network.area)
        if identity in seen:
            raise CommandCompileError(
                f"OSPF network {parsed} in area {network.area} is duplicated"
            )
        seen.add(identity)
        count += 1
        body.append(f"network {rendered}")
    if count == 0:
        raise CommandCompileError("at least one OSPF network is required")
    if default_information_originate:
        body.append("default-information originate")
    shows = (
        ["show running-config | include router ospf| network |area"]
        if show
        else []
    )
    return config_plan(device, "ospf", body, show_commands=shows)
