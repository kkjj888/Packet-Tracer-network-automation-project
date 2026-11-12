"""IPv4 NAT/PAT command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


@dataclass(frozen=True)
class PatConfig:
    acl_id: str
    source_network: str
    inside_interfaces: tuple[str, ...]
    outside_interface: str

    def rendered(self) -> tuple[str, str, tuple[str, ...], str]:
        if not self.acl_id.isdigit() or not 1 <= int(self.acl_id) <= 99:
            raise CommandCompileError("NAT ACL ID must be 1-99")
        try:
            network = ipaddress.ip_network(self.source_network, strict=True)
        except ValueError as exc:
            raise CommandCompileError(f"invalid NAT source network: {exc}") from exc
        if network.version != 4:
            raise CommandCompileError("only IPv4 PAT is supported")
        inside = tuple(
            require_port(value, "NAT inside interface")
            for value in self.inside_interfaces
        )
        if not inside:
            raise CommandCompileError("PAT requires at least one inside interface")
        if len(set(inside)) != len(inside):
            raise CommandCompileError("PAT inside interfaces must be unique")
        outside = require_port(self.outside_interface, "NAT outside interface")
        if outside in inside:
            raise CommandCompileError(
                "NAT outside interface cannot also be an inside interface"
            )
        wildcard = ipaddress.IPv4Address(int(network.netmask) ^ 0xFFFFFFFF)
        acl = (
            f"access-list {self.acl_id} permit "
            f"{network.network_address} {wildcard}"
        )
        return acl, str(network), inside, outside


@dataclass(frozen=True)
class StaticNatConfig:
    protocol: str
    inside_address: str
    inside_port: int
    outside_address: str
    outside_port: int
    inside_interfaces: tuple[str, ...]
    outside_interface: str

    def rendered(self) -> tuple[str, tuple[str, ...], str]:
        if self.protocol not in ("tcp", "udp"):
            raise CommandCompileError("static NAT protocol must be tcp or udp")
        try:
            local = ipaddress.ip_address(self.inside_address)
            global_address = ipaddress.ip_address(self.outside_address)
        except ValueError as exc:
            raise CommandCompileError(f"invalid static NAT address: {exc}") from exc
        if local.version != 4 or global_address.version != 4:
            raise CommandCompileError("only IPv4 static NAT is supported")
        if not 1 <= self.inside_port <= 65535:
            raise CommandCompileError("static NAT inside port must be 1-65535")
        if not 1 <= self.outside_port <= 65535:
            raise CommandCompileError("static NAT outside port must be 1-65535")
        inside = tuple(
            require_port(value, "NAT inside interface")
            for value in self.inside_interfaces
        )
        if not inside:
            raise CommandCompileError("static NAT requires inside interfaces")
        if len(set(inside)) != len(inside):
            raise CommandCompileError("static NAT inside interfaces must be unique")
        outside = require_port(self.outside_interface, "NAT outside interface")
        if outside in inside:
            raise CommandCompileError(
                "NAT outside interface cannot also be an inside interface"
            )
        command = (
            f"ip nat inside source static {self.protocol} {local} "
            f"{self.inside_port} {global_address} {self.outside_port}"
        )
        return command, inside, outside


def compile_pat_config(
    device: str,
    configs: Iterable[PatConfig],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen_acl: set[str] = set()
    count = 0
    for config in configs:
        acl, _, inside, outside = config.rendered()
        if config.acl_id in seen_acl:
            raise CommandCompileError(f"NAT ACL {config.acl_id} is duplicated")
        seen_acl.add(config.acl_id)
        body.append(acl)
        for interface in inside:
            body.extend(
                [
                    f"interface {interface}",
                    "ip nat inside",
                    "exit",
                ]
            )
        body.extend(
            [
                f"interface {outside}",
                "ip nat outside",
                "exit",
                (
                    f"ip nat inside source list {config.acl_id} "
                    f"interface {outside} overload"
                ),
            ]
        )
        count += 1
    if count == 0:
        raise CommandCompileError("at least one PAT configuration is required")
    shows = ["show ip nat translations"] if show else []
    return config_plan(device, "nat-pat", body, show_commands=shows)


def compile_static_nat_config(
    device: str,
    configs: Iterable[StaticNatConfig],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    configured_inside: set[str] = set()
    configured_outside: set[str] = set()
    seen: set[tuple[str, str, int, str, int]] = set()
    count = 0
    for config in configs:
        command, inside, outside = config.rendered()
        identity = (
            config.protocol,
            config.inside_address,
            config.inside_port,
            config.outside_address,
            config.outside_port,
        )
        if identity in seen:
            raise CommandCompileError(f"static NAT mapping {identity} is duplicated")
        seen.add(identity)
        body.append(command)
        for interface in inside:
            if interface not in configured_inside:
                configured_inside.add(interface)
                body.extend(
                    [f"interface {interface}", "ip nat inside", "exit"]
                )
        if outside not in configured_outside:
            configured_outside.add(outside)
            body.extend([f"interface {outside}", "ip nat outside", "exit"])
        count += 1
    if not count:
        raise CommandCompileError("at least one static NAT mapping is required")
    shows = ["show ip nat translations"] if show else []
    return config_plan(device, "nat-static", body, show_commands=shows)
