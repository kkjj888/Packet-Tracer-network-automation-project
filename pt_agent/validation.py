"""Schema, network-semantic, and command-safety validation."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml
from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schema" / "network.schema.json"
DEFAULT_VLAN_IDS = frozenset({1, 1002, 1003, 1004, 1005})


@dataclass(frozen=True)
class ValidationIssue:
    """One machine-readable validation failure or warning."""

    severity: str
    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass
class ValidationResult:
    """Combined validation result for a network DSL document."""

    schema_issues: list[ValidationIssue]
    semantic_issues: list[ValidationIssue]

    @property
    def issues(self) -> list[ValidationIssue]:
        return [*self.schema_issues, *self.semantic_issues]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "error_count": sum(
                issue.severity == "error" for issue in self.issues
            ),
            "warning_count": sum(
                issue.severity == "warning" for issue in self.issues
            ),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def load_yaml_document(path: str | Path) -> Mapping[str, object]:
    """Load one YAML document and reject non-mapping roots."""

    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError("DSL root must be a mapping")
    return document


def load_json_schema(path: str | Path = DEFAULT_SCHEMA_PATH) -> Mapping:
    """Load and validate the JSON Schema itself."""

    schema_path = Path(path)
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


class NetworkValidator:
    """Validate network structure and deterministic network semantics."""

    def __init__(self, schema_path: str | Path = DEFAULT_SCHEMA_PATH) -> None:
        self.schema = load_json_schema(schema_path)
        self.schema_validator = Draft202012Validator(self.schema)

    def validate(self, document: Mapping[str, object]) -> ValidationResult:
        schema_issues = self._validate_schema(document)
        semantic_issues = self._validate_semantics(document)
        return ValidationResult(schema_issues, semantic_issues)

    def _validate_schema(
        self, document: Mapping[str, object]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for error in sorted(
            self.schema_validator.iter_errors(document),
            key=lambda item: list(item.absolute_path),
        ):
            path = _json_path(error.absolute_path)
            issues.append(
                ValidationIssue(
                    "error",
                    "SCHEMA_VALIDATION",
                    path,
                    error.message,
                )
            )
        return issues

    def _validate_semantics(
        self, document: Mapping[str, object]
    ) -> list[ValidationIssue]:
        checker = _SemanticChecker(document)
        return checker.run()


class _SemanticChecker:
    def __init__(self, document: Mapping[str, object]) -> None:
        self.document = document
        self.issues: list[ValidationIssue] = []
        raw_devices = document.get("devices", [])
        self.devices = {
            str(device.get("id")): device
            for device in raw_devices
            if isinstance(device, dict) and device.get("id")
        }
        self.ipv4 = [
            item
            for item in _as_list(document.get("ipv4"))
            if isinstance(item, dict)
        ]
        self.vlans = {
            int(vlan["id"]): vlan
            for vlan in _as_list(document.get("vlans"))
            if isinstance(vlan, dict) and isinstance(vlan.get("id"), int)
        }

    def run(self) -> list[ValidationIssue]:
        self._check_devices()
        self._check_links()
        self._check_ipv4()
        self._check_vlans()
        self._check_static_routes()
        self._check_rip()
        self._check_ospf()
        self._check_acls()
        self._check_acl_bindings()
        self._check_verification()
        return self.issues

    def error(self, code: str, path: str, message: str) -> None:
        self.issues.append(ValidationIssue("error", code, path, message))

    def warning(self, code: str, path: str, message: str) -> None:
        self.issues.append(ValidationIssue("warning", code, path, message))

    def _check_devices(self) -> None:
        seen: set[str] = set()
        for index, device in enumerate(_as_list(self.document.get("devices"))):
            if not isinstance(device, dict):
                continue
            device_id = str(device.get("id", ""))
            path = f"devices[{index}].id"
            if device_id in seen:
                self.error(
                    "DUPLICATE_DEVICE_ID",
                    path,
                    f"device id {device_id!r} is duplicated",
                )
            seen.add(device_id)

    def _check_links(self) -> None:
        used_ports: dict[tuple[str, str], str] = {}
        for index, link in enumerate(_as_list(self.document.get("links"))):
            if not isinstance(link, dict):
                continue
            endpoints = []
            for side in ("from", "to"):
                raw = str(link.get(side, ""))
                parsed = _parse_endpoint(raw)
                if parsed is None:
                    self.error(
                        "INVALID_ENDPOINT",
                        f"links[{index}].{side}",
                        f"invalid endpoint {raw!r}; expected device:port",
                    )
                    continue
                device_id, port = parsed
                if device_id not in self.devices:
                    self.error(
                        "UNKNOWN_DEVICE",
                        f"links[{index}].{side}",
                        f"unknown device {device_id!r}",
                    )
                key = (device_id, port)
                if key in used_ports:
                    self.error(
                        "PORT_ALREADY_CONNECTED",
                        f"links[{index}].{side}",
                        (
                            f"{device_id}:{port} is already used by "
                            f"{used_ports[key]}"
                        ),
                    )
                used_ports[key] = f"links[{index}].{side}"
                endpoints.append(key)
            if len(endpoints) == 2 and endpoints[0] == endpoints[1]:
                self.error(
                    "LOOPBACK_LINK",
                    f"links[{index}]",
                    "a link cannot connect a port to itself",
                )

    def _check_ipv4(self) -> None:
        addresses: dict[str, str] = {}
        ports: set[tuple[str, str]] = set()
        for index, item in enumerate(self.ipv4):
            path = f"ipv4[{index}]"
            device_id = str(item.get("device", ""))
            port = str(item.get("port", ""))
            if device_id not in self.devices:
                self.error(
                    "UNKNOWN_DEVICE",
                    f"{path}.device",
                    f"unknown device {device_id!r}",
                )
            key = (device_id, port)
            if key in ports:
                self.error(
                    "DUPLICATE_INTERFACE_ADDRESS",
                    path,
                    f"{device_id}:{port} has more than one IPv4 address",
                )
            ports.add(key)

            try:
                interface = ipaddress.ip_interface(str(item.get("address", "")))
            except ValueError as exc:
                self.error(
                    "INVALID_IPV4_ADDRESS",
                    f"{path}.address",
                    str(exc),
                )
                continue
            if interface.version != 4:
                self.error(
                    "INVALID_IPV4_ADDRESS",
                    f"{path}.address",
                    "only IPv4 is supported by this schema version",
                )
                continue
            previous = addresses.get(str(interface.ip))
            if previous is not None:
                self.error(
                    "DUPLICATE_IPV4_ADDRESS",
                    f"{path}.address",
                    f"{interface.ip} is also used at {previous}",
                )
            addresses[str(interface.ip)] = f"{path}.address"

            if interface.network.prefixlen < 31:
                if interface.ip == interface.network.network_address:
                    self.error(
                        "NETWORK_ADDRESS_ASSIGNED",
                        f"{path}.address",
                        f"{interface.ip} is the network address",
                    )
                if interface.ip == interface.network.broadcast_address:
                    self.error(
                        "BROADCAST_ADDRESS_ASSIGNED",
                        f"{path}.address",
                        f"{interface.ip} is the broadcast address",
                    )

            gateway = item.get("gateway")
            if gateway is None:
                continue
            try:
                gateway_ip = ipaddress.ip_address(str(gateway))
            except ValueError as exc:
                self.error(
                    "INVALID_GATEWAY",
                    f"{path}.gateway",
                    str(exc),
                )
                continue
            if gateway_ip not in interface.network:
                self.error(
                    "GATEWAY_OUTSIDE_SUBNET",
                    f"{path}.gateway",
                    (
                        f"gateway {gateway_ip} is outside "
                        f"{interface.network}"
                    ),
                )
            if gateway_ip == interface.ip:
                self.error(
                    "GATEWAY_IS_LOCAL_ADDRESS",
                    f"{path}.gateway",
                    "gateway cannot equal the interface address",
                )

    def _check_vlans(self) -> None:
        names: dict[str, int] = {}
        for vlan_id, vlan in self.vlans.items():
            name = str(vlan.get("name", ""))
            if name.lower() in names:
                self.warning(
                    "DUPLICATE_VLAN_NAME",
                    f"vlans.{vlan_id}.name",
                    (
                        f"VLAN name {name!r} is also used by "
                        f"VLAN {names[name.lower()]}"
                    ),
                )
            names[name.lower()] = vlan_id

        seen_ports: set[tuple[str, str]] = set()
        for index, item in enumerate(
            _as_list(self.document.get("vlan_assignments"))
        ):
            if not isinstance(item, dict):
                continue
            path = f"vlan_assignments[{index}]"
            device_id = str(item.get("device", ""))
            port = str(item.get("port", ""))
            mode = str(item.get("mode", ""))
            device = self.devices.get(device_id)
            if device is None:
                self.error(
                    "UNKNOWN_DEVICE",
                    f"{path}.device",
                    f"unknown device {device_id!r}",
                )
            elif device.get("type") != "switch":
                self.error(
                    "VLAN_ASSIGNMENT_REQUIRES_SWITCH",
                    f"{path}.device",
                    f"{device_id} is not a switch",
                )
            key = (device_id, port)
            if key in seen_ports:
                self.error(
                    "DUPLICATE_VLAN_ASSIGNMENT",
                    path,
                    f"{device_id}:{port} has multiple switching assignments",
                )
            seen_ports.add(key)
            if mode == "access":
                vlan_id = item.get("vlan")
                if not isinstance(vlan_id, int):
                    self.error(
                        "ACCESS_VLAN_REQUIRED",
                        f"{path}.vlan",
                        "an access port requires a VLAN",
                    )
                elif not self._vlan_is_defined(vlan_id):
                    self.error(
                        "UNKNOWN_VLAN_REFERENCE",
                        f"{path}.vlan",
                        f"VLAN {vlan_id} is not defined",
                    )
            elif mode == "trunk":
                for field in ("native_vlan",):
                    vlan_id = item.get(field)
                    if (
                        isinstance(vlan_id, int)
                        and not self._vlan_is_defined(vlan_id)
                    ):
                        self.error(
                            "UNKNOWN_VLAN_REFERENCE",
                            f"{path}.{field}",
                            f"VLAN {vlan_id} is not defined",
                        )
                for allowed in _as_list(item.get("allowed_vlans")):
                    if (
                        isinstance(allowed, int)
                        and not self._vlan_is_defined(allowed)
                    ):
                        self.error(
                            "UNKNOWN_VLAN_REFERENCE",
                            f"{path}.allowed_vlans",
                            f"VLAN {allowed} is not defined",
                        )

    def _vlan_is_defined(self, vlan_id: int) -> bool:
        return vlan_id in self.vlans or vlan_id in DEFAULT_VLAN_IDS

    def _router_device(self, value: object, path: str) -> bool:
        device_id = str(value)
        device = self.devices.get(device_id)
        if device is None:
            self.error(
                "UNKNOWN_DEVICE",
                path,
                f"unknown device {device_id!r}",
            )
            return False
        if device.get("type") != "router":
            self.error(
                "ROUTER_REQUIRED",
                path,
                f"{device_id} is not a router",
            )
            return False
        return True

    def _check_static_routes(self) -> None:
        routing = self.document.get("routing")
        if not isinstance(routing, dict):
            return
        for index, route in enumerate(_as_list(routing.get("static"))):
            if not isinstance(route, dict):
                continue
            path = f"routing.static[{index}]"
            if not self._router_device(route.get("device"), f"{path}.device"):
                continue
            try:
                network = ipaddress.ip_network(str(route.get("network", "")))
                next_hop = ipaddress.ip_address(str(route.get("next_hop", "")))
            except ValueError as exc:
                self.error("INVALID_STATIC_ROUTE", path, str(exc))
                continue
            if network.version != 4 or next_hop.version != 4:
                self.error(
                    "INVALID_STATIC_ROUTE",
                    path,
                    "only IPv4 static routes are supported",
                )
                continue
            if not self._next_hop_reachable(
                str(route.get("device")), next_hop, route.get("interface")
            ):
                self.error(
                    "ROUTE_NEXT_HOP_UNREACHABLE",
                    f"{path}.next_hop",
                    (
                        f"{next_hop} is not inside a connected subnet on "
                        f"{route.get('device')}"
                    ),
                )

    def _next_hop_reachable(
        self,
        device_id: str,
        next_hop: ipaddress.IPv4Address,
        interface_name: object = None,
    ) -> bool:
        for item in self.ipv4:
            if str(item.get("device")) != device_id:
                continue
            if interface_name and str(item.get("port")) != str(interface_name):
                continue
            try:
                interface = ipaddress.ip_interface(str(item.get("address")))
            except ValueError:
                continue
            if next_hop in interface.network:
                return True
        return False

    def _check_rip(self) -> None:
        routing = self.document.get("routing")
        if not isinstance(routing, dict) or not isinstance(
            routing.get("rip"), dict
        ):
            return
        rip = routing["rip"]
        for index, device_id in enumerate(_as_list(rip.get("devices"))):
            self._router_device(device_id, f"routing.rip.devices[{index}]")
        if rip.get("version") == 2 and rip.get("auto_summary") is True:
            self.warning(
                "RIPV2_AUTO_SUMMARY_ENABLED",
                "routing.rip.auto_summary",
                "RIPv2 auto-summary is enabled and may hide VLSM routes",
            )
        for index, network in enumerate(_as_list(rip.get("networks"))):
            try:
                parsed = ipaddress.ip_address(str(network))
            except ValueError as exc:
                self.error(
                    "INVALID_RIP_NETWORK",
                    f"routing.rip.networks[{index}]",
                    str(exc),
                )
                continue
            if parsed.version != 4:
                self.error(
                    "INVALID_RIP_NETWORK",
                    f"routing.rip.networks[{index}]",
                    "only IPv4 RIPv2 networks are supported",
                )

    def _check_ospf(self) -> None:
        routing = self.document.get("routing")
        if not isinstance(routing, dict) or not isinstance(
            routing.get("ospf"), dict
        ):
            return
        ospf = routing["ospf"]
        configured_devices = {
            str(value) for value in _as_list(ospf.get("devices"))
        }
        for index, device_id in enumerate(_as_list(ospf.get("devices"))):
            self._router_device(device_id, f"routing.ospf.devices[{index}]")
        for index, item in enumerate(_as_list(ospf.get("networks"))):
            if not isinstance(item, dict):
                continue
            path = f"routing.ospf.networks[{index}]"
            device_id = str(item.get("device", ""))
            if device_id not in configured_devices:
                self.error(
                    "OSPF_DEVICE_NOT_CONFIGURED",
                    f"{path}.device",
                    f"{device_id} is not listed in routing.ospf.devices",
                )
            if not self._router_device(device_id, f"{path}.device"):
                continue
            try:
                raw_network = ipaddress.ip_interface(
                    str(item.get("network", ""))
                )
            except ValueError as exc:
                self.error("INVALID_OSPF_NETWORK", f"{path}.network", str(exc))
                continue
            network = raw_network.network
            if network.version != 4:
                self.error(
                    "INVALID_OSPF_NETWORK",
                    f"{path}.network",
                    "only IPv4 OSPF is supported",
                )
                continue
            if raw_network.ip != network.network_address:
                self.error(
                    "NON_CANONICAL_NETWORK",
                    f"{path}.network",
                    "OSPF network must use its network address",
                )
            if not self._network_reachable(device_id, network):
                self.error(
                    "OSPF_NETWORK_NOT_CONNECTED",
                    f"{path}.network",
                    f"{network} does not contain an interface on {device_id}",
                )

    def _network_reachable(
        self, device_id: str, network: ipaddress.IPv4Network
    ) -> bool:
        for item in self.ipv4:
            if str(item.get("device")) != device_id:
                continue
            try:
                interface = ipaddress.ip_interface(str(item.get("address")))
            except ValueError:
                continue
            if interface.ip in network:
                return True
        return False

    def _check_acls(self) -> None:
        seen: set[str] = set()
        for index, acl in enumerate(_as_list(self.document.get("acls"))):
            if not isinstance(acl, dict):
                continue
            path = f"acls[{index}]"
            acl_id = str(acl.get("id", ""))
            if acl_id in seen:
                self.error(
                    "DUPLICATE_ACL_ID",
                    f"{path}.id",
                    f"ACL {acl_id!r} is duplicated",
                )
            seen.add(acl_id)
            if acl_id.isdigit() and not 1 <= int(acl_id) <= 99:
                self.warning(
                    "STANDARD_ACL_RANGE",
                    f"{path}.id",
                    "standard ACL IDs are normally 1-99 or 1300-1999",
                )
            for rule_index, rule in enumerate(_as_list(acl.get("rules"))):
                if not isinstance(rule, dict):
                    continue
                rule_path = f"{path}.rules[{rule_index}]"
                match = rule.get("match")
                if match in ("host", "network"):
                    try:
                        ipaddress.ip_address(str(rule.get("address", "")))
                    except ValueError as exc:
                        self.error(
                            "INVALID_ACL_ADDRESS",
                            f"{rule_path}.address",
                            str(exc),
                        )
                if match == "network":
                    try:
                        wildcard = ipaddress.IPv4Address(
                            str(rule.get("wildcard", ""))
                        )
                    except ValueError as exc:
                        self.error(
                            "INVALID_ACL_WILDCARD",
                            f"{rule_path}.wildcard",
                            str(exc),
                        )
                        continue
                    mask = int(wildcard) ^ 0xFFFFFFFF
                    try:
                        ipaddress.IPv4Network((0, mask))
                    except ValueError:
                        self.error(
                            "NON_CONTIGUOUS_ACL_WILDCARD",
                            f"{rule_path}.wildcard",
                            f"{wildcard} is not a contiguous wildcard mask",
                        )

    def _check_acl_bindings(self) -> None:
        acls = {
            str(acl.get("id"))
            for acl in _as_list(self.document.get("acls"))
            if isinstance(acl, dict) and acl.get("id")
        }
        for index, binding in enumerate(
            _as_list(self.document.get("acl_bindings"))
        ):
            if not isinstance(binding, dict):
                continue
            path = f"acl_bindings[{index}]"
            device_id = str(binding.get("device", ""))
            if not self._router_device(device_id, f"{path}.device"):
                continue
            acl_id = str(binding.get("acl", ""))
            if acl_id not in acls:
                self.error(
                    "UNKNOWN_ACL_REFERENCE",
                    f"{path}.acl",
                    f"ACL {acl_id!r} is not defined",
                )

    def _check_verification(self) -> None:
        verification = self.document.get("verification")
        if not isinstance(verification, dict):
            return
        for index, test in enumerate(
            _as_list(verification.get("connectivity"))
        ):
            if not isinstance(test, dict):
                continue
            path = f"verification.connectivity[{index}]"
            source = str(test.get("source", ""))
            destination = str(test.get("destination", ""))
            if source not in self.devices:
                self.error(
                    "UNKNOWN_DEVICE",
                    f"{path}.source",
                    f"unknown source device {source!r}",
                )
            if destination not in self.devices:
                self.error(
                    "UNKNOWN_DEVICE",
                    f"{path}.destination",
                    f"unknown destination device {destination!r}",
                )
            if source == destination:
                self.error(
                    "SELF_CONNECTIVITY_TEST",
                    path,
                    "source and destination must be different devices",
                )


_DANGEROUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^reload(?:\s|$)", re.I), "reload"),
    (re.compile(r"^write\s+erase(?:\s|$)", re.I), "write erase"),
    (re.compile(r"^erase\s+startup-config(?:\s|$)", re.I), "erase startup"),
    (re.compile(r"^format(?:\s|$)", re.I), "format"),
    (re.compile(r"^delete(?:\s|$)", re.I), "delete"),
    (re.compile(r"^confreg(?:\s|$)", re.I), "configuration register"),
    (re.compile(r"^debug\s+all(?:\s|$)", re.I), "debug all"),
    (re.compile(r"^no\s+ip\s+routing(?:\s|$)", re.I), "disable routing"),
)

_ALLOWED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^enable$", re.I),
    re.compile(r"^configure terminal$", re.I),
    re.compile(r"^exit$", re.I),
    re.compile(r"^end$", re.I),
    re.compile(r"^write memory$", re.I),
    re.compile(r"^hostname [A-Za-z][A-Za-z0-9_-]{0,31}$", re.I),
    re.compile(r"^interface [A-Za-z0-9/._-]+$", re.I),
    re.compile(r"^no shutdown$", re.I),
    re.compile(r"^ip address (?:\d{1,3}\.){3}\d{1,3} (?:\d{1,3}\.){3}\d{1,3}$", re.I),
    re.compile(r"^vlan \d{1,4}$", re.I),
    re.compile(r"^name [A-Za-z0-9_-]{1,32}$", re.I),
    re.compile(r"^switchport mode (?:access|trunk)$", re.I),
    re.compile(r"^switchport access vlan \d{1,4}$", re.I),
    re.compile(r"^switchport trunk native vlan \d{1,4}$", re.I),
    re.compile(r"^switchport trunk allowed vlan (?:all|\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)$", re.I),
    re.compile(r"^access-list [A-Za-z0-9_-]+ (?:permit|deny) .+$", re.I),
    re.compile(r"^ip access-group [A-Za-z0-9_-]+ (?:in|out)$", re.I),
    re.compile(r"^router (?:rip|ospf(?: \d{1,5})?)$", re.I),
    re.compile(r"^version [12]$", re.I),
    re.compile(r"^(?:no )?auto-summary$", re.I),
    re.compile(r"^network (?:\d{1,3}\.){3}\d{1,3}$", re.I),
    re.compile(
        r"^network (?:\d{1,3}\.){3}\d{1,3} "
        r"(?:\d{1,3}\.){3}\d{1,3} area (?:0|[1-9]\d*)$",
        re.I,
    ),
    re.compile(
        r"^ip route (?:\d{1,3}\.){3}\d{1,3} "
        r"(?:\d{1,3}\.){3}\d{1,3} "
        r"(?:\d{1,3}\.){3}\d{1,3}(?: \d{1,3})?$",
        re.I,
    ),
    re.compile(r"^show [A-Za-z0-9/|._ -]+$", re.I),
)


class CommandSafetyValidator:
    """Fail closed for commands outside the supported IOS subset."""

    def validate(
        self,
        commands: Sequence[str],
        *,
        max_commands: int = 200,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not commands:
            return [
                ValidationIssue(
                    "error",
                    "EMPTY_COMMAND_SEQUENCE",
                    "commands",
                    "command sequence must not be empty",
                )
            ]
        if len(commands) > max_commands:
            issues.append(
                ValidationIssue(
                    "error",
                    "COMMAND_LIMIT_EXCEEDED",
                    "commands",
                    f"{len(commands)} commands exceed limit {max_commands}",
                )
            )
        for index, raw in enumerate(commands):
            path = f"commands[{index}]"
            if not isinstance(raw, str):
                issues.append(
                    ValidationIssue(
                        "error",
                        "COMMAND_NOT_STRING",
                        path,
                        "command must be a string",
                    )
                )
                continue
            command = raw.strip()
            if not command:
                issues.append(
                    ValidationIssue(
                        "error",
                        "EMPTY_COMMAND",
                        path,
                        "empty command is not allowed",
                    )
                )
                continue
            if "\n" in raw or "\r" in raw:
                issues.append(
                    ValidationIssue(
                        "error",
                        "NEWLINE_IN_COMMAND",
                        path,
                        "one command string must contain exactly one command",
                    )
                )
                continue
            if any(token in command for token in ("`", "$(", "&&", "||", ";")):
                issues.append(
                    ValidationIssue(
                        "error",
                        "COMMAND_INJECTION_PATTERN",
                        path,
                        f"unsafe shell-like token in {command!r}",
                    )
                )
            dangerous = next(
                (
                    description
                    for pattern, description in _DANGEROUS_PATTERNS
                    if pattern.search(command)
                ),
                None,
            )
            if dangerous is not None:
                issues.append(
                    ValidationIssue(
                        "error",
                        "DANGEROUS_COMMAND",
                        path,
                        f"blocked dangerous command {dangerous!r}",
                    )
                )
                continue
            if not any(pattern.search(command) for pattern in _ALLOWED_PATTERNS):
                issues.append(
                    ValidationIssue(
                        "error",
                        "COMMAND_NOT_ALLOWLISTED",
                        path,
                        f"command is not allowlisted: {command!r}",
                    )
                )
        return issues


def validate_network_file(
    path: str | Path,
    *,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> ValidationResult:
    document = load_yaml_document(path)
    return NetworkValidator(schema_path).validate(document)


def validate_commands(commands: Iterable[str]) -> list[ValidationIssue]:
    return CommandSafetyValidator().validate(list(commands))


def _parse_endpoint(value: str) -> tuple[str, str] | None:
    if ":" not in value:
        return None
    device_id, port = value.split(":", 1)
    if not device_id or not port:
        return None
    return device_id, port


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _json_path(parts: Iterable[object]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result
