"""Helpers for deploying and evaluating a compiled network DSL."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Mapping

from .dsl_compiler import CompiledNetwork, VerificationSpec


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


def evaluate_verification(
    spec: VerificationSpec,
    ping: Mapping[str, object],
    destination_address: str,
) -> VerificationResult:
    if spec.protocol != "ping":
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
