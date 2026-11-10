"""Deterministic fault diagnosis rules for the PT backend."""

from __future__ import annotations

import ipaddress
from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class Diagnosis:
    code: str
    device: str
    port: str
    message: str
    expected: object
    actual: object

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def diagnose_host_address(
    *,
    expected: Mapping[str, str],
    observed: Mapping[str, str],
    peer_ip: str,
) -> Diagnosis | None:
    device = str(observed.get("device", expected.get("device", "")))
    port = str(observed.get("port", expected.get("port", "")))
    expected_ip = str(expected["ip"])
    expected_mask = str(expected["mask"])
    actual_ip = str(observed.get("ip", ""))
    actual_mask = str(observed.get("mask", ""))

    if actual_ip != expected_ip:
        return Diagnosis(
            code="HOST_IP_MISMATCH",
            device=device,
            port=port,
            message=(
                f"{device}:{port} expected IP {expected_ip}, "
                f"PT reports {actual_ip}"
            ),
            expected=expected_ip,
            actual=actual_ip,
        )

    if actual_mask != expected_mask:
        return Diagnosis(
            code="HOST_MASK_MISMATCH",
            device=device,
            port=port,
            message=(
                f"{device}:{port} expected mask {expected_mask}, "
                f"PT reports {actual_mask}"
            ),
            expected=expected_mask,
            actual=actual_mask,
        )

    try:
        interface = ipaddress.ip_interface(f"{actual_ip}/{actual_mask}")
        peer = ipaddress.ip_address(peer_ip)
    except ValueError as exc:
        return Diagnosis(
            code="INVALID_HOST_ADDRESS",
            device=device,
            port=port,
            message=f"Invalid host address: {exc}",
            expected=f"{expected_ip}/{expected_mask}",
            actual=f"{actual_ip}/{actual_mask}",
        )

    if peer not in interface.network:
        return Diagnosis(
            code="PEER_OUTSIDE_HOST_SUBNET",
            device=device,
            port=port,
            message=(
                f"{device}:{port} network {interface.network} does not contain "
                f"peer {peer_ip}"
            ),
            expected=f"peer {peer_ip} inside {interface.network}",
            actual=str(interface.network),
        )
    return None

