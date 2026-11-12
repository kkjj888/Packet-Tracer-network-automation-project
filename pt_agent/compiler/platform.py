"""Multilayer-switch services: routed interfaces, SVIs, HSRP, and STP."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Iterable

from .base import CommandCompileError, CommandPlan, config_plan, require_port


_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]{1,80}$")


@dataclass(frozen=True)
class RoutedSwitchPort:
    port: str
    address: str
    point_to_point: bool = False

    def rendered(self) -> str:
        port = require_port(self.port)
        try:
            interface = ipaddress.ip_interface(self.address)
        except ValueError as exc:
            raise CommandCompileError(
                f"invalid routed switch-port address {self.address!r}: {exc}"
            ) from exc
        if interface.version != 4:
            raise CommandCompileError("only IPv4 routed switch ports are supported")
        return (
            f"interface {port}|no switchport|"
            f"ip address {interface.ip} {interface.netmask}"
            + ("|ip ospf network point-to-point" if self.point_to_point else "")
        )


@dataclass(frozen=True)
class SviConfig:
    vlan: int
    address: str

    def rendered(self) -> tuple[int, str]:
        if not isinstance(self.vlan, int) or not 1 <= self.vlan <= 4094:
            raise CommandCompileError("SVI VLAN must be an integer from 1 to 4094")
        try:
            interface = ipaddress.ip_interface(self.address)
        except ValueError as exc:
            raise CommandCompileError(f"invalid SVI address: {exc}") from exc
        if interface.version != 4:
            raise CommandCompileError("only IPv4 SVIs are supported")
        return self.vlan, f"{interface.ip} {interface.netmask}"


@dataclass(frozen=True)
class HsrpGroup:
    vlan: int
    group: int
    virtual_ip: str
    priority: int = 100
    preempt: bool = True
    track_port: str | None = None
    track_decrement: int = 10

    def rendered(self) -> list[str]:
        if not isinstance(self.vlan, int) or not 1 <= self.vlan <= 4094:
            raise CommandCompileError("HSRP VLAN must be an integer from 1 to 4094")
        if not isinstance(self.group, int) or not 0 <= self.group <= 255:
            raise CommandCompileError("HSRP group must be 0-255")
        try:
            virtual_ip = ipaddress.ip_address(self.virtual_ip)
        except ValueError as exc:
            raise CommandCompileError(f"invalid HSRP virtual IP: {exc}") from exc
        if virtual_ip.version != 4:
            raise CommandCompileError("only IPv4 HSRP is supported")
        if not isinstance(self.priority, int) or not 1 <= self.priority <= 255:
            raise CommandCompileError("HSRP priority must be 1-255")
        commands = [
            f"standby {self.group} ip {virtual_ip}",
            f"standby {self.group} priority {self.priority}",
        ]
        if self.preempt:
            commands.append(f"standby {self.group} preempt")
        if self.track_port:
            port = require_port(self.track_port, "HSRP tracked port")
            if not isinstance(self.track_decrement, int) or not (
                1 <= self.track_decrement <= 255
            ):
                raise CommandCompileError(
                    "HSRP track decrement must be 1-255"
                )
            commands.append(
                f"standby {self.group} track {port} {self.track_decrement}"
            )
        return commands


@dataclass(frozen=True)
class StpConfig:
    role: str
    vlans: tuple[int, ...]
    priority: int | None = None

    def rendered(self) -> str:
        if not self.vlans or any(
            not isinstance(vlan, int) or not 1 <= vlan <= 4094
            for vlan in self.vlans
        ):
            raise CommandCompileError("STP VLANs must be integers from 1 to 4094")
        vlan_text = _compress_vlans(sorted(set(self.vlans)))
        if self.role in ("primary", "secondary"):
            return f"spanning-tree vlan {vlan_text} root {self.role}"
        if self.role == "priority":
            if (
                not isinstance(self.priority, int)
                or not 0 <= self.priority <= 61440
                or self.priority % 4096
            ):
                raise CommandCompileError(
                    "STP priority must be a multiple of 4096 from 0 to 61440"
                )
            return f"spanning-tree vlan {vlan_text} priority {self.priority}"
        raise CommandCompileError("STP role must be primary, secondary, or priority")


def compile_switch_routing(
    device: str,
    *,
    show: bool = True,
) -> CommandPlan:
    shows = ["show ip route"] if show else []
    return config_plan(device, "switch-routing", ["ip routing"], show_commands=shows)


def compile_routed_switch_ports(
    device: str,
    ports: Iterable[RoutedSwitchPort],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[str] = set()
    count = 0
    for item in ports:
        rendered = item.rendered().split("|")
        port = rendered[0].removeprefix("interface ")
        if port in seen:
            raise CommandCompileError(f"routed switch port {port} is duplicated")
        seen.add(port)
        body.extend([*rendered, "no shutdown", "exit"])
        count += 1
    if not count:
        raise CommandCompileError("at least one routed switch port is required")
    shows = ["show ip interface brief"] if show else []
    return config_plan(
        device,
        "routed-switch-ports",
        body,
        show_commands=shows,
    )


def compile_svi_config(
    device: str,
    interfaces: Iterable[SviConfig],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[int] = set()
    count = 0
    for item in interfaces:
        vlan, address = item.rendered()
        if vlan in seen:
            raise CommandCompileError(f"SVI VLAN {vlan} is duplicated")
        seen.add(vlan)
        body.extend(
            [
                f"interface Vlan{vlan}",
                f"ip address {address}",
                "no shutdown",
                "exit",
            ]
        )
        count += 1
    if not count:
        raise CommandCompileError("at least one SVI is required")
    shows = ["show ip interface brief"] if show else []
    return config_plan(device, "svi", body, show_commands=shows)


def compile_hsrp_config(
    device: str,
    groups: Iterable[HsrpGroup],
    *,
    show: bool = True,
) -> CommandPlan:
    body: list[str] = []
    seen: set[tuple[int, int]] = set()
    count = 0
    for group in groups:
        key = (group.vlan, group.group)
        if key in seen:
            raise CommandCompileError(
                f"HSRP VLAN {group.vlan} group {group.group} is duplicated"
            )
        seen.add(key)
        body.append(f"interface Vlan{group.vlan}")
        body.extend(group.rendered())
        body.append("exit")
        count += 1
    if not count:
        raise CommandCompileError("at least one HSRP group is required")
    shows = ["show standby brief"] if show else []
    return config_plan(device, "hsrp", body, show_commands=shows)


def compile_stp_config(
    device: str,
    configs: Iterable[StpConfig],
    *,
    show: bool = True,
) -> CommandPlan:
    body = [config.rendered() for config in configs]
    if not body:
        raise CommandCompileError("at least one STP configuration is required")
    shows = ["show spanning-tree summary"] if show else []
    return config_plan(device, "stp", body, show_commands=shows)


def compile_management_config(
    device: str,
    *,
    domain_name: str,
    username: str,
    password: str,
    access_acl: str | None = None,
    show: bool = True,
) -> CommandPlan:
    domain_name = domain_name.strip()
    username = username.strip()
    password = password.strip()
    if not _DOMAIN_RE.fullmatch(domain_name):
        raise CommandCompileError("management domain name is invalid")
    if not _USERNAME_RE.fullmatch(username):
        raise CommandCompileError("management username is invalid")
    if len(password) < 6 or len(password) > 64 or any(
        char.isspace() for char in password
    ):
        raise CommandCompileError(
            "management password must be 6-64 non-whitespace characters"
        )
    body = [
        "ip domain-name " + domain_name,
        f"username {username} privilege 15 secret {password}",
        "line vty 0 4",
    ]
    if access_acl:
        body.append(f"access-class {access_acl} in")
    body.extend(["login local", "transport input ssh", "exit"])
    shows = ["show running-config | include username|transport|access-class"] if show else []
    return config_plan(device, "management", body, show_commands=shows)


def _compress_vlans(vlans: list[int]) -> str:
    ranges: list[str] = []
    start = previous = vlans[0]
    for vlan in vlans[1:]:
        if vlan == previous + 1:
            previous = vlan
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = vlan
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ",".join(ranges)
