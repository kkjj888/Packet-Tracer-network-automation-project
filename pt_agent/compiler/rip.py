"""RIPv1/RIPv2 command templates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan


@dataclass(frozen=True)
class RipConfig:
    version: int
    networks: tuple[str, ...]
    auto_summary: bool = True

    def rendered_networks(self) -> tuple[ipaddress.IPv4Address, ...]:
        if self.version not in (1, 2):
            raise CommandCompileError("RIP version must be 1 or 2")
        if self.version == 1 and not self.auto_summary:
            raise CommandCompileError("RIPv1 does not support no auto-summary")
        if not self.networks:
            raise CommandCompileError("RIP requires at least one network")
        rendered: list[ipaddress.IPv4Address] = []
        seen: set[str] = set()
        for value in self.networks:
            try:
                network = ipaddress.ip_address(value)
            except ValueError as exc:
                raise CommandCompileError(
                    f"invalid RIP network {value!r}: {exc}"
                ) from exc
            if network.version != 4:
                raise CommandCompileError("only IPv4 RIP is supported")
            text = str(network)
            if text in seen:
                raise CommandCompileError(f"RIP network {text} is duplicated")
            seen.add(text)
            rendered.append(network)
        return tuple(rendered)


def compile_rip_config(
    device: str,
    config: RipConfig,
    *,
    show: bool = True,
) -> CommandPlan:
    networks = config.rendered_networks()
    body = [
        "router rip",
        f"version {config.version}",
        "auto-summary" if config.auto_summary else "no auto-summary",
        *(f"network {network}" for network in networks),
    ]
    shows = (
        [
            "show running-config | include "
            "router rip|version|auto-summary|network"
        ]
        if show
        else []
    )
    return config_plan(device, "rip", body, show_commands=shows)
