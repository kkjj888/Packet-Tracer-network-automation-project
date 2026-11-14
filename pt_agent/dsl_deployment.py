"""Helpers for deploying and evaluating a compiled network DSL."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Mapping

from .dsl_compiler import (
    CompiledNetwork,
    RouteAssertionSpec,
    TracerouteSpec,
    VerificationSpec,
)


class DslDeploymentError(ValueError):
    """Compiled intent cannot be evaluated or deployed safely."""


@dataclass(frozen=True)
class VerificationResult:
    name: str
    source: str
    destination: str
    destination_ip: str
    expected: str
    actual: str
    passed: bool
    ping: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source,
            "destination": self.destination,
            "destination_ip": self.destination_ip,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "ping": dict(self.ping),
        }


@dataclass(frozen=True)
class RouteAssertionResult:
    device: str
    destination: str
    protocol: str
    passed: bool
    matched_entries: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "device": self.device,
            "destination": self.destination,
            "protocol": self.protocol,
            "passed": self.passed,
            "matched_entries": list(self.matched_entries),
        }


@dataclass(frozen=True)
class TracerouteResult:
    name: str
    source: str
    destination: str
    expected_hops: tuple[str, ...]
    actual_hops: tuple[str, ...]
    complete: bool
    passed: bool
    raw_output: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source,
            "destination": self.destination,
            "expected_hops": list(self.expected_hops),
            "actual_hops": list(self.actual_hops),
            "complete": self.complete,
            "passed": self.passed,
            "raw_output": self.raw_output,
        }


_ROUTE_PROTOCOLS = {
    "66": "bgp",
    "67": "connected",
    "76": "local",
    "79": "ospf",
    "82": "rip",
    "83": "static",
}


def host_ip_by_device(network: CompiledNetwork) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in network.host_addresses:
        if item.device in result:
            raise DslDeploymentError(
                f"host device {item.device} has multiple IPv4 addresses"
            )
        try:
            interface = ipaddress.ip_interface(item.address)
        except ValueError as exc:
            raise DslDeploymentError(
                f"invalid host address for {item.device}: {exc}"
            ) from exc
        result[item.device] = str(interface.ip)
    return result


def host_ipv6_by_device(network: CompiledNetwork) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in network.host_ipv6_addresses:
        if item.device in result:
            raise DslDeploymentError(
                f"host device {item.device} has multiple IPv6 addresses"
            )
        try:
            interface = ipaddress.ip_interface(item.address)
        except ValueError as exc:
            raise DslDeploymentError(
                f"invalid IPv6 host address for {item.device}: {exc}"
            ) from exc
        result[item.device] = str(interface.ip)
    return result


def destination_ip(
    network: CompiledNetwork,
    device: str,
) -> str:
    addresses = host_ip_by_device(network)
    try:
        return addresses[device]
    except KeyError as exc:
        raise DslDeploymentError(
            f"verification destination {device} has no IPv4 address"
        ) from exc


def destination_ipv6(
    network: CompiledNetwork,
    device: str,
) -> str:
    addresses = host_ipv6_by_device(network)
    try:
        return addresses[device]
    except KeyError as exc:
        raise DslDeploymentError(
            f"verification destination {device} has no IPv6 address"
        ) from exc


def evaluate_verification(
    spec: VerificationSpec,
    ping: Mapping[str, object],
    destination_address: str,
) -> VerificationResult:
    if spec.protocol not in ("ping", "ping6"):
        raise DslDeploymentError(
            f"unsupported verification protocol {spec.protocol!r}"
        )
    if spec.expected not in ("pass", "fail"):
        raise DslDeploymentError(
            f"unsupported expected result {spec.expected!r}"
        )
    success = bool(ping.get("success"))
    complete = bool(ping.get("complete"))
    if spec.expected == "pass":
        passed = success and complete
    else:
        passed = not success
    actual = "pass" if success and complete else "fail"
    return VerificationResult(
        spec.name,
        spec.source,
        spec.destination,
        destination_address,
        spec.expected,
        actual,
        passed,
        ping,
    )


def evaluate_route_assertion(
    spec: RouteAssertionSpec,
    routing_state: Mapping[str, object],
) -> RouteAssertionResult:
    destination = ipaddress.ip_network(spec.destination, strict=True)
    matched: list[dict[str, object]] = []
    for network in routing_state.get("networks", []):
        if not isinstance(network, dict):
            continue
        if (
            str(network.get("network")) != str(destination.network_address)
            or str(network.get("mask")) != str(destination.netmask)
        ):
            continue
        for entry in network.get("entries", []):
            if not isinstance(entry, dict):
                continue
            protocol = _ROUTE_PROTOCOLS.get(str(entry.get("protocol")))
            if protocol != spec.protocol:
                continue
            if spec.next_hop and str(entry.get("nextHop")) != spec.next_hop:
                continue
            if spec.interface and str(entry.get("port")) != spec.interface:
                continue
            if (
                spec.admin_distance is not None
                and int(entry.get("adminDistance", -1)) != spec.admin_distance
            ):
                continue
            matched.append(dict(entry))
    return RouteAssertionResult(
        spec.device,
        str(destination),
        spec.protocol,
        bool(matched),
        tuple(matched),
    )


_TRACEROUTE_HOP_RE = re.compile(
    r"^\s*\d+\s+.*?\s((?:\d{1,3}\.){3}\d{1,3})\s*$",
    re.MULTILINE,
)


def parse_traceroute_hops(output: str) -> tuple[str, ...]:
    return tuple(_TRACEROUTE_HOP_RE.findall(output))


def evaluate_traceroute(
    spec: TracerouteSpec,
    output: str,
) -> TracerouteResult:
    actual = parse_traceroute_hops(output)
    complete = "Trace complete" in output or "trace complete" in output.lower()
    return TracerouteResult(
        spec.name,
        spec.source,
        spec.destination,
        spec.expected_hops,
        actual,
        complete,
        complete and actual == spec.expected_hops,
        output,
    )
