"""Standard numbered ACL command templates."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Iterable, Literal

from .base import CommandCompileError, CommandPlan, config_plan, require_port


@dataclass(frozen=True)
class AclRule:
    action: Literal["permit", "deny"]
    match: Literal["any", "host", "network"]
    address: str | None = None
    wildcard: str | None = None

    def rendered(self) -> str:
        if self.action not in ("permit", "deny"):
            raise CommandCompileError("ACL action must be permit or deny")
        if self.match == "any":
            if self.address is not None or self.wildcard is not None:
                raise CommandCompileError("ACL any rule cannot include an address")
            return "any"
        if self.match == "host":
            if self.address is None or self.wildcard is not None:
                raise CommandCompileError(
                    "ACL host rule requires address and no wildcard"
                )
            address = _ipv4_address(self.address, "ACL host address")
            return f"host {address}"
        if self.match == "network":
            if self.address is None or self.wildcard is None:
                raise CommandCompileError(
                    "ACL network rule requires address and wildcard"
                )
            address = _ipv4_address(self.address, "ACL network address")
            wildcard = _ipv4_address(self.wildcard, "ACL wildcard")
            mask = int(ipaddress.IPv4Address(wildcard)) ^ 0xFFFFFFFF
            wildcard_bits = mask ^ 0xFFFFFFFF
            if wildcard_bits & (wildcard_bits + 1):
                raise CommandCompileError(
                    f"ACL wildcard {wildcard} is not contiguous"
                )
            return f"{address} {wildcard}"
        raise CommandCompileError("ACL match must be any, host, or network")


@dataclass(frozen=True)
class AclEndpoint:
    kind: Literal["any", "host", "network"]
    address: str | None = None
    wildcard: str | None = None

    def rendered(self) -> str:
        if self.kind == "any":
            if self.address is not None or self.wildcard is not None:
                raise CommandCompileError("ACL any endpoint cannot have an address")
            return "any"
        if self.kind == "host":
            if self.address is None or self.wildcard is not None:
                raise CommandCompileError("ACL host endpoint requires an address")
            return f"host {_ipv4_address(self.address, 'ACL host address')}"
        if self.kind == "network":
            if self.address is None or self.wildcard is None:
                raise CommandCompileError(
                    "ACL network endpoint requires address and wildcard"
                )
            address = _ipv4_address(self.address, "ACL network address")
            wildcard = _ipv4_address(self.wildcard, "ACL wildcard")
            mask = int(ipaddress.IPv4Address(wildcard)) ^ 0xFFFFFFFF
            wildcard_bits = mask ^ 0xFFFFFFFF
            if wildcard_bits & (wildcard_bits + 1):
                raise CommandCompileError(
                    f"ACL wildcard {wildcard} is not contiguous"
                )
            return f"{address} {wildcard}"
        raise CommandCompileError("ACL endpoint must be any, host, or network")


@dataclass(frozen=True)
class ExtendedAclRule:
    action: Literal["permit", "deny"]
    protocol: Literal["ip", "tcp", "udp", "icmp"]
    source: AclEndpoint
    destination: AclEndpoint
    destination_port_eq: int | str | None = None
    icmp_type: str | None = None
    established: bool = False

    def rendered(self) -> str:
        if self.action not in ("permit", "deny"):
            raise CommandCompileError("ACL action must be permit or deny")
        if self.protocol not in ("ip", "tcp", "udp", "icmp"):
            raise CommandCompileError("extended ACL protocol is invalid")
        if self.protocol == "icmp" and self.destination_port_eq is not None:
            raise CommandCompileError("ICMP ACL cannot use a port")
        if self.protocol != "icmp" and self.icmp_type is not None:
            raise CommandCompileError("ICMP type is only valid for ICMP rules")
        parts = [
            self.protocol,
            self.source.rendered(),
            self.destination.rendered(),
        ]
        if self.destination_port_eq is not None:
            port = _port(self.destination_port_eq)
            parts.extend(["eq", port])
        if self.icmp_type:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", self.icmp_type):
                raise CommandCompileError("ICMP type is invalid")
            parts.append(self.icmp_type)
        if self.established:
            if self.protocol != "tcp":
                raise CommandCompileError("established is only valid for TCP")
            parts.append("established")
        return " ".join(parts)


@dataclass(frozen=True)
class AclDefinition:
    acl_id: str
    rules: tuple[AclRule | ExtendedAclRule, ...]
    kind: Literal["standard", "extended"] = "standard"

    def rendered_id(self) -> str:
        text = self.acl_id.strip()
        if not text:
            raise CommandCompileError("ACL ID must not be empty")
        if text.isdigit():
            value = int(text)
            if self.kind == "standard" and not (
                1 <= value <= 99 or 1300 <= value <= 1999
            ):
                raise CommandCompileError(
                    "standard ACL ID must be 1-99 or 1300-1999"
                )
            if self.kind == "extended" and not (
                100 <= value <= 199 or 2000 <= value <= 2699
            ):
                raise CommandCompileError(
                    "extended ACL ID must be 100-199 or 2000-2699"
                )
        if self.kind not in ("standard", "extended"):
            raise CommandCompileError("ACL kind must be standard or extended")
        return text


@dataclass(frozen=True)
class AclBinding:
    interface: str
    direction: Literal["in", "out"]

    def rendered(self) -> tuple[str, str]:
        port = require_port(self.interface, "ACL interface")
        if self.direction not in ("in", "out"):
            raise CommandCompileError("ACL direction must be in or out")
        return port, self.direction


def compile_acl_config(
    device: str,
    acl: AclDefinition,
    bindings: Iterable[AclBinding],
    *,
    show: bool = True,
    require_binding: bool = True,
) -> CommandPlan:
    acl_id = acl.rendered_id()
    if not acl.rules:
        raise CommandCompileError("ACL must contain at least one rule")
    body: list[str] = []
    for rule in acl.rules:
        if acl.kind == "standard" and not isinstance(rule, AclRule):
            raise CommandCompileError(
                "standard ACLs require standard address rules"
            )
        if acl.kind == "extended" and not isinstance(rule, ExtendedAclRule):
            raise CommandCompileError(
                "extended ACLs require protocol/source/destination rules"
            )
        body.append(f"access-list {acl_id} {rule.action} {rule.rendered()}")

    seen: set[tuple[str, str]] = set()
    binding_count = 0
    for binding in bindings:
        port, direction = binding.rendered()
        key = (port, direction)
        if key in seen:
            raise CommandCompileError(
                f"ACL binding {port} {direction} is duplicated"
            )
        seen.add(key)
        binding_count += 1
        body.extend(
            [
                f"interface {port}",
                f"ip access-group {acl_id} {direction}",
                "exit",
            ]
        )
    if binding_count == 0 and require_binding:
        raise CommandCompileError("at least one ACL binding is required")
    shows = [f"show access-lists {acl_id}"] if show else []
    return config_plan(device, "acl", body, show_commands=shows)


def _ipv4_address(value: str, field: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise CommandCompileError(f"invalid {field}: {value!r}") from exc
    if address.version != 4:
        raise CommandCompileError(f"{field} must be IPv4")
    return str(address)


def _port(value: int | str) -> str:
    if isinstance(value, int):
        if not 1 <= value <= 65535:
            raise CommandCompileError("ACL port must be 1-65535")
        return str(value)
    names = {
        "bootpc",
        "bootps",
        "domain",
        "www",
        "https",
        "ssh",
        "telnet",
        "ftp",
        "smtp",
    }
    text = value.strip().lower()
    if text not in names:
        raise CommandCompileError(f"unknown ACL port name {value!r}")
    return text
