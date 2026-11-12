"""VLAN and access-port command templates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


_VLAN_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


@dataclass(frozen=True)
class VlanDefinition:
    vlan_id: int
    name: str

    def rendered(self) -> tuple[int, str]:
        if not isinstance(self.vlan_id, int) or not 1 <= self.vlan_id <= 4094:
            raise CommandCompileError("VLAN ID must be an integer from 1 to 4094")
        name = self.name.strip()
        if not _VLAN_NAME_RE.fullmatch(name):
            raise CommandCompileError(
                "VLAN name must match [A-Za-z0-9_-]{1,32}"
            )
        return self.vlan_id, name


@dataclass(frozen=True)
class AccessPort:
    port: str
    vlan_id: int


def compile_vlan_config(
    device: str,
    vlans: Iterable[VlanDefinition],
    access_ports: Iterable[AccessPort] = (),
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    vlan_ids: set[int] = {1, 1002, 1003, 1004, 1005}
    names: set[str] = set()
    vlan_count = 0
    for vlan in vlans:
        vlan_id, name = vlan.rendered()
        if vlan_id in vlan_ids:
            raise CommandCompileError(f"VLAN {vlan_id} is duplicated or default")
        if name.lower() in names:
            raise CommandCompileError(f"VLAN name {name!r} is duplicated")
        vlan_ids.add(vlan_id)
        names.add(name.lower())
        vlan_count += 1
        body.extend(
            [
                f"vlan {vlan_id}",
                f"name {name}",
                "exit",
            ]
        )
    if vlan_count == 0:
        raise CommandCompileError("at least one VLAN is required")

    seen_ports: set[str] = set()
    for assignment in access_ports:
        port = require_port(assignment.port)
        if port in seen_ports:
            raise CommandCompileError(f"access port {port} is duplicated")
        if assignment.vlan_id not in vlan_ids:
            raise CommandCompileError(
                f"access port {port} references undefined VLAN "
                f"{assignment.vlan_id}"
            )
        seen_ports.add(port)
        body.extend(
            [
                f"interface {port}",
                "switchport mode access",
                f"switchport access vlan {assignment.vlan_id}",
                "no shutdown",
                "exit",
            ]
        )

    shows = ["show vlan brief"] if show else []
    return config_plan(device, "vlan", body, show_commands=shows)
