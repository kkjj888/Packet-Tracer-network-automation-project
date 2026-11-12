"""802.1Q trunk command templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


@dataclass(frozen=True)
class TrunkPort:
    port: str
    native_vlan: int = 1
    allowed_vlans: tuple[int, ...] | None = None

    def rendered(self) -> tuple[str, int, str]:
        port = require_port(self.port)
        if not isinstance(self.native_vlan, int) or not (
            1 <= self.native_vlan <= 4094
        ):
            raise CommandCompileError(
                "trunk native VLAN must be an integer from 1 to 4094"
            )
        if self.allowed_vlans is None:
            allowed = "all"
        else:
            vlan_ids = list(self.allowed_vlans)
            if not vlan_ids:
                raise CommandCompileError("trunk allowed VLAN list must not be empty")
            if any(
                not isinstance(vlan_id, int) or not 1 <= vlan_id <= 4094
                for vlan_id in vlan_ids
            ):
                raise CommandCompileError(
                    "trunk allowed VLANs must be integers from 1 to 4094"
                )
            if len(set(vlan_ids)) != len(vlan_ids):
                raise CommandCompileError("trunk allowed VLANs must be unique")
            if self.native_vlan not in vlan_ids:
                raise CommandCompileError(
                    "trunk native VLAN must be present in allowed VLANs"
                )
            allowed = _compress_vlans(sorted(vlan_ids))
        return port, self.native_vlan, allowed


def _compress_vlans(vlans: list[int]) -> str:
    ranges: list[str] = []
    start = previous = vlans[0]
    for vlan_id in vlans[1:]:
        if vlan_id == previous + 1:
            previous = vlan_id
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = vlan_id
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges)


def compile_trunk_config(
    device: str,
    trunks: Iterable[TrunkPort],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[str] = set()
    count = 0
    for trunk in trunks:
        port, native_vlan, allowed = trunk.rendered()
        if port in seen:
            raise CommandCompileError(f"trunk port {port} is duplicated")
        seen.add(port)
        count += 1
        body.extend(
            [
                f"interface {port}",
                "switchport mode trunk",
                f"switchport trunk native vlan {native_vlan}",
                f"switchport trunk allowed vlan {allowed}",
                "no shutdown",
                "exit",
            ]
        )
    if count == 0:
        raise CommandCompileError("at least one trunk port is required")
    shows = ["show interfaces trunk"] if show else []
    return config_plan(device, "trunk", body, show_commands=shows)
