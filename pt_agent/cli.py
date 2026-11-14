"""Command-line entry point for the backend bootstrap milestone."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .application import CompilationService, NetworkValidationService
from .audit import JsonlAuditLogger
from .diagnostics import diagnose_host_address
from .dsl_compiler import (
    CompiledNetwork,
    DslCompileError,
    RouteAssertionSpec,
    TracerouteSpec,
    VerificationSpec,
    compile_network_dsl,
    topology_js,
    topology_devices_js,
    topology_links_js,
)
from .dsl_deployment import (
    DslDeploymentError,
    destination_ip,
    destination_ipv6,
    evaluate_route_assertion,
    evaluate_traceroute,
    evaluate_verification,
)
from .jobs import JobManager, JobOptions
from .config_suite import (
    acl_apply_commands,
    acl_router_config_commands,
    acl_topology_js,
    ospf_config_commands,
    rip_config_commands,
    routed_two_router_topology_js,
    show_acl_commands,
    show_ospf_config_commands,
    show_rip_config_commands,
    show_vlan_commands,
    trunk_switch_config_commands,
    trunk_topology_js,
    vlan_switch_config_commands,
    vlan_topology_js,
)
from .script_backend import (
    acl_state_js,
    associate_wireless_client_js,
    configure_dhcp_client_js,
    configure_host_ipv6_js,
    configure_host_ip_js,
    configure_acl_js,
    configure_router_ipv4_js,
    configure_static_routes_js,
    configure_switch_vlans_js,
    configure_trunk_port_js,
    configure_wireless_ap_js,
    enter_ios_command_js,
    fast_forward_js,
    file_size_js,
    host_ip_state_js,
    host_ipv6_state_js,
    install_module_js,
    minimal_topology_js,
    new_project_js,
    open_project_js,
    read_command_output_js,
    routing_state_js,
    save_project_js,
    set_port_power_js,
    start_ping_js,
    start_traceroute_js,
    swap_laptop_to_wireless_js,
    switch_vlan_state_js,
    terminal_state_js,
    topology_state_js,
    trunk_port_state_js,
    router_ipv4_state_js,
)
from .script_bridge import PTBridgeServer, ScriptBridgeError
from .runtime import WindowsPacketTracerRuntime
from .validation import (
    DEFAULT_SCHEMA_PATH,
    CommandSafetyError,
    CommandSafetyValidator,
    NetworkValidator,
    load_yaml_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _json_print(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _jobs_root(args: argparse.Namespace) -> Path:
    configured = getattr(args, "data_dir", None)
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (PROJECT_ROOT / "artifacts" / "jobs").resolve()
    )


def _job_manager(
    args: argparse.Namespace,
    *,
    recover: bool = False,
) -> JobManager:
    return JobManager(
        workspace_root=PROJECT_ROOT,
        data_root=_jobs_root(args),
        recover=recover,
    )


def _dhcp_leases_are_valid(
    leases: object,
    network_prefixes: tuple[str, ...],
) -> bool:
    if not isinstance(leases, list) or not network_prefixes:
        return True
    networks = tuple(ipaddress.ip_network(value, strict=True) for value in network_prefixes)
    for lease in leases:
        if not isinstance(lease, dict):
            return False
        try:
            address = ipaddress.ip_address(str(lease.get("ip", "")))
        except ValueError:
            return False
        if address.is_link_local or address.is_unspecified:
            return False
        if not any(address in network for network in networks):
            return False
    return True


def _pt_runtime(args: argparse.Namespace) -> WindowsPacketTracerRuntime:
    return WindowsPacketTracerRuntime(
        PROJECT_ROOT,
        pt_root=getattr(args, "pt_root", None),
    )


def command_doctor(args: argparse.Namespace) -> int:
    payload = _pt_runtime(args).doctor()
    payload["python"] = sys.version
    payload["python_executable"] = sys.executable
    _json_print(payload)
    return 0 if not payload["validation_errors"] else 1


def command_validate_dsl(args: argparse.Namespace) -> int:
    payload = NetworkValidationService(
        workspace_root=PROJECT_ROOT,
        schema_path=Path(args.schema),
    ).validate(args.path)
    _json_print(payload)
    return 0 if payload["valid"] else 1


def command_check_commands(args: argparse.Namespace) -> int:
    issues = CommandSafetyValidator().validate(list(args.commands))
    _json_print(
        {
            "safe": not issues,
            "commands": list(args.commands),
            "issues": [issue.to_dict() for issue in issues],
        }
    )
    return 0 if not issues else 1


def command_compile_dsl(args: argparse.Namespace) -> int:
    payload = CompilationService(workspace_root=PROJECT_ROOT).compile(
        args.path,
        output=args.output,
    )
    _json_print(payload)
    return 0 if payload["compiled"] else 1


def command_launch_gui(args: argparse.Namespace) -> int:
    process = _pt_runtime(args).launch()
    _json_print(
        {
            "pid": process.pid,
            "message": (
                "Open Extensions > Scripting > Configure PT Script Modules, "
                "add vendor/mcp-bridge.pts, then launch MCP Bridge."
            ),
        }
    )
    return 0


def command_script_bridge(args: argparse.Namespace) -> int:
    server = PTBridgeServer(port=args.bridge_port, result_timeout=args.result_timeout)
    server.start()
    _json_print(
        {
            "status": "listening",
            "url": f"http://127.0.0.1:{server.port}",
            "next_step": (
                "Open Packet Tracer and launch Extensions > MCP Bridge. "
                "Press Ctrl+C here to stop the bridge."
            ),
        }
    )
    try:
        while True:
            time.sleep(1)
            if server.connected:
                print("extension=connected", flush=True)
                break
    except KeyboardInterrupt:
        server.stop()
        return 0

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


def command_script_demo(args: argparse.Namespace) -> int:
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    project_path = (artifacts / "script-engine-smoke.pkt").resolve()
    report_path = (artifacts / "script-engine-smoke.json").resolve()

    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "status": "starting",
        "bridge_url": f"http://127.0.0.1:{args.bridge_port}",
        "project_path": str(project_path),
    }
    try:
        bridge.start()
        bridge.wait_for_extension(timeout=args.connect_timeout)
        report["extension_status"] = bridge.status()

        report["new_project"] = bridge.execute_json(new_project_js())
        report["create_topology"] = bridge.execute_json(minimal_topology_js())
        report["before_save"] = bridge.execute_json(topology_state_js())

        if project_path.exists():
            project_path.unlink()
        report["save_dispatch"] = bridge.execute_json(save_project_js(project_path))

        deadline = time.monotonic() + args.save_timeout
        file_state: dict[str, object] = {"exists": False, "size": 0}
        while time.monotonic() < deadline:
            raw_state = bridge.execute_json(file_size_js(project_path))
            if isinstance(raw_state, dict):
                file_state = raw_state
            if file_state.get("exists") and int(file_state.get("size", 0)) > 0:
                break
            time.sleep(0.5)
        report["saved_file"] = file_state
        if not file_state.get("exists") or int(file_state.get("size", 0)) <= 0:
            raise ScriptBridgeError("PT did not create the saved PKT file")

        bridge.execute_json(new_project_js())
        report["reopen"] = bridge.execute_json(open_project_js(project_path))
        time.sleep(1)
        report["after_reopen"] = bridge.execute_json(topology_state_js())
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


def parse_ping_output(output: str) -> dict[str, object]:
    sent_match = re.search(r"Sent\s*=\s*(\d+)", output, re.IGNORECASE)
    received_match = re.search(r"Received\s*=\s*(\d+)", output, re.IGNORECASE)
    lost_match = re.search(r"Lost\s*=\s*(\d+)", output, re.IGNORECASE)
    average_match = re.search(
        r"Average\s*=\s*([0-9.]+)\s*ms", output, re.IGNORECASE
    )

    replies = len(re.findall(r"\bReply from\b", output, re.IGNORECASE))
    timeouts = len(
        re.findall(r"Request timed out", output, re.IGNORECASE)
    )
    has_summary = bool(sent_match and received_match and lost_match)
    if has_summary:
        sent = int(sent_match.group(1))
        received = int(received_match.group(1))
        lost = int(lost_match.group(1))
    else:
        sent = replies + timeouts
        received = replies
        lost = timeouts
    complete = has_summary or sent >= 4
    success = complete and sent > 0 and received == sent and lost == 0
    success_rate = round((received / sent) * 100, 2) if sent else 0.0
    return {
        "success": success,
        "complete": complete,
        "sent": sent,
        "received": received,
        "lost": lost,
        "success_rate": success_rate,
        "average_ms": (
            float(average_match.group(1)) if average_match else None
        ),
        "raw_output": output,
    }


def _run_ping(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    *,
    label: str,
    device: str,
    destination: str,
    timeout: float,
) -> dict[str, object]:
    ping_start = _logged_command(
        bridge,
        audit,
        f"{label}_dispatch",
        start_ping_js(device, destination),
    )
    if not isinstance(ping_start, dict) or "outputStart" not in ping_start:
        raise ScriptBridgeError(f"Invalid ping start result: {ping_start!r}")
    offset = int(ping_start["outputStart"])

    output = ""
    parsed: dict[str, object] = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        candidate = _logged_read(
            bridge,
            audit,
            f"{label}_read_output",
            read_command_output_js(device, offset),
            timeout=min(max(timeout / 3, 4.0), 10.0),
        )
        if isinstance(candidate, dict) and isinstance(candidate.get("output"), str):
            output = str(candidate["output"])
            parsed = parse_ping_output(output)
            if parsed.get("complete"):
                return parsed
    return parsed or {"success": False, "complete": False, "raw_output": output}


def _run_traceroute(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    *,
    label: str,
    device: str,
    destination: str,
    timeout: float,
) -> dict[str, object]:
    start = _logged_command(
        bridge,
        audit,
        f"{label}_dispatch",
        start_traceroute_js(device, destination),
    )
    if not isinstance(start, dict) or "outputStart" not in start:
        raise ScriptBridgeError(f"Invalid traceroute start result: {start!r}")
    offset = int(start["outputStart"])
    output = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        candidate = _logged_read(
            bridge,
            audit,
            f"{label}_read_output",
            read_command_output_js(device, offset),
            timeout=min(max(timeout / 3, 4.0), 12.0),
        )
        if isinstance(candidate, dict) and isinstance(candidate.get("output"), str):
            output = str(candidate["output"])
            if "trace complete" in output.lower():
                break
    return {
        "complete": "trace complete" in output.lower(),
        "raw_output": output,
    }


def _logged_command(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    label: str,
    expression: str,
    timeout: float | None = None,
) -> object:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        attempt_label = f"{label}_attempt_{attempt}"
        audit.record(
            "command_dispatch",
            label=attempt_label,
            javascript=expression,
        )
        try:
            result = bridge.execute_json(expression, timeout=timeout)
        except Exception as exc:
            last_error = exc
            audit.record(
                "command_failed",
                label=attempt_label,
                error=f"{type(exc).__name__}: {exc}",
            )
            if "device_not_found" not in str(exc) or attempt == 3:
                raise
            time.sleep(0.5)
            continue
        audit.record("command_result", label=attempt_label, result=result)
        return result
    assert last_error is not None
    raise last_error


def _logged_read(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    label: str,
    expression: str,
    *,
    timeout: float = 12.0,
    attempts: int = 2,
) -> object:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _logged_command(
                bridge,
                audit,
                f"{label}_attempt_{attempt}",
                expression,
                timeout=timeout,
            )
        except ScriptBridgeError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def command_config_ping_demo(args: argparse.Namespace) -> int:
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    project_path = (artifacts / "config-ping-smoke.pkt").resolve()
    report_path = (artifacts / "config-ping-smoke.json").resolve()
    audit_path = (artifacts / "config-ping-audit.jsonl").resolve()

    run_id = f"config-ping-{uuid.uuid4().hex[:12]}"
    audit = JsonlAuditLogger(audit_path, run_id)
    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "run_id": run_id,
        "status": "starting",
        "project_path": str(project_path),
        "audit_path": str(audit_path),
    }
    audit.record(
        "run_started",
        intent={
            "device1": "PC1",
            "device2": "PC2",
            "pc1_ip": "192.168.1.10",
            "pc2_ip": "192.168.1.11",
            "mask": "255.255.255.0",
        },
    )

    try:
        bridge.start()
        audit.record(
            "bridge_started",
            url=f"http://127.0.0.1:{bridge.port}",
        )
        bridge.wait_for_extension(timeout=args.connect_timeout)
        audit.record("extension_connected", status=bridge.status())

        _logged_command(bridge, audit, "new_project", new_project_js())
        topology = _logged_command(
            bridge, audit, "create_topology", minimal_topology_js()
        )
        report["topology"] = topology
        _logged_command(bridge, audit, "fast_forward", fast_forward_js())

        pc1_ip = _logged_command(
            bridge,
            audit,
            "configure_pc1_ip",
            configure_host_ip_js(
                "PC1", "FastEthernet0", "192.168.1.10", "255.255.255.0"
            ),
        )
        pc2_ip = _logged_command(
            bridge,
            audit,
            "configure_pc2_ip",
            configure_host_ip_js(
                "PC2", "FastEthernet0", "192.168.1.11", "255.255.255.0"
            ),
        )
        report["pc1_config"] = pc1_ip
        report["pc2_config"] = pc2_ip

        pc1_readback = _logged_command(
            bridge,
            audit,
            "readback_pc1_ip",
            host_ip_state_js("PC1", "FastEthernet0"),
        )
        pc2_readback = _logged_command(
            bridge,
            audit,
            "readback_pc2_ip",
            host_ip_state_js("PC2", "FastEthernet0"),
        )
        report["pc1_readback"] = pc1_readback
        report["pc2_readback"] = pc2_readback

        _logged_command(bridge, audit, "fast_forward_after_config", fast_forward_js())
        time.sleep(1)
        warmup = _run_ping(
            bridge,
            audit,
            label="ping_warmup",
            device="PC1",
            destination="192.168.1.11",
            timeout=args.ping_timeout,
        )
        report["ping_warmup"] = warmup
        time.sleep(1)

        ping_result = _run_ping(
            bridge,
            audit,
            label="ping_verification",
            device="PC1",
            destination="192.168.1.11",
            timeout=args.ping_timeout,
        )
        report["ping"] = ping_result
        if not ping_result or not ping_result.get("success"):
            raise ScriptBridgeError(
                f"Ping verification failed: {ping_result!r}"
            )

        if project_path.exists():
            project_path.unlink()
        _logged_command(
            bridge,
            audit,
            "save_project",
            save_project_js(project_path),
        )

        file_state: dict[str, object] = {"exists": False, "size": 0}
        deadline = time.monotonic() + args.save_timeout
        while time.monotonic() < deadline:
            state = _logged_command(
                bridge,
                audit,
                "check_saved_file",
                file_size_js(project_path),
            )
            if isinstance(state, dict):
                file_state = state
            if file_state.get("exists") and int(file_state.get("size", 0)) > 0:
                break
            time.sleep(0.4)
        report["saved_file"] = file_state
        if not file_state.get("exists") or int(file_state.get("size", 0)) <= 0:
            raise ScriptBridgeError("PT did not save the configured PKT")

        _logged_command(bridge, audit, "new_project_for_reopen", new_project_js())
        _logged_command(
            bridge,
            audit,
            "reopen_project",
            open_project_js(project_path),
        )
        time.sleep(1)
        reopened_pc1 = _logged_command(
            bridge,
            audit,
            "reopened_pc1_ip",
            host_ip_state_js("PC1", "FastEthernet0"),
        )
        reopened_pc2 = _logged_command(
            bridge,
            audit,
            "reopened_pc2_ip",
            host_ip_state_js("PC2", "FastEthernet0"),
        )
        report["reopened_pc1"] = reopened_pc1
        report["reopened_pc2"] = reopened_pc2

        expected = {
            "pc1_ip": "192.168.1.10",
            "pc2_ip": "192.168.1.11",
            "mask": "255.255.255.0",
            "ping_success": True,
        }
        actual = {
            "pc1_ip": (
                reopened_pc1.get("ip") if isinstance(reopened_pc1, dict) else None
            ),
            "pc2_ip": (
                reopened_pc2.get("ip") if isinstance(reopened_pc2, dict) else None
            ),
            "mask": (
                reopened_pc1.get("mask")
                if isinstance(reopened_pc1, dict)
                else None
            ),
            "ping_success": bool(ping_result.get("success")),
        }
        passed = actual == expected
        report["expected"] = expected
        report["actual"] = actual
        report["status"] = "passed" if passed else "failed"
        audit.record(
            "verification_finished",
            status=report["status"],
            expected=expected,
            actual=actual,
        )
        if not passed:
            raise ScriptBridgeError(
                f"Post-reopen verification mismatch: expected={expected!r}, "
                f"actual={actual!r}"
            )
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        audit.record(
            "run_failed",
            status="failed",
            error=report["error"],
        )
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


def command_repair_demo(args: argparse.Namespace) -> int:
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    project_path = (artifacts / "repair-smoke.pkt").resolve()
    report_path = (artifacts / "repair-smoke.json").resolve()
    audit_path = (artifacts / "repair-audit.jsonl").resolve()

    expected_pc1 = {
        "device": "PC1",
        "port": "FastEthernet0",
        "ip": "192.168.1.10",
        "mask": "255.255.255.0",
    }
    expected_pc2 = {
        "device": "PC2",
        "port": "FastEthernet0",
        "ip": "192.168.1.20",
        "mask": "255.255.255.0",
    }
    wrong_pc1 = {
        **expected_pc1,
        "mask": "255.255.255.252",
    }

    run_id = f"repair-{uuid.uuid4().hex[:12]}"
    audit = JsonlAuditLogger(audit_path, run_id)
    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "run_id": run_id,
        "status": "starting",
        "project_path": str(project_path),
        "audit_path": str(audit_path),
        "expected": {"pc1": expected_pc1, "pc2": expected_pc2},
        "injected_fault": {
            "code": "HOST_MASK_MISMATCH",
            "device": "PC1",
            "expected_mask": expected_pc1["mask"],
            "injected_mask": wrong_pc1["mask"],
        },
    }
    audit.record(
        "run_started",
        expected={"pc1": expected_pc1, "pc2": expected_pc2},
        injected_fault=report["injected_fault"],
    )

    try:
        bridge.start()
        audit.record("bridge_started", url=f"http://127.0.0.1:{bridge.port}")
        bridge.wait_for_extension(timeout=args.connect_timeout)
        audit.record("extension_connected", status=bridge.status())

        _logged_command(bridge, audit, "new_project", new_project_js())
        report["topology"] = _logged_command(
            bridge, audit, "create_topology", minimal_topology_js()
        )

        _logged_command(
            bridge,
            audit,
            "configure_pc1_expected",
            configure_host_ip_js(
                "PC1",
                "FastEthernet0",
                expected_pc1["ip"],
                expected_pc1["mask"],
            ),
        )
        _logged_command(
            bridge,
            audit,
            "configure_pc2_expected",
            configure_host_ip_js(
                "PC2",
                "FastEthernet0",
                expected_pc2["ip"],
                expected_pc2["mask"],
            ),
        )
        _logged_command(bridge, audit, "fast_forward_baseline", fast_forward_js())
        time.sleep(1)

        _run_ping(
            bridge,
            audit,
            label="baseline_warmup",
            device="PC1",
            destination=expected_pc2["ip"],
            timeout=args.ping_timeout,
        )
        baseline = _run_ping(
            bridge,
            audit,
            label="baseline_verification",
            device="PC1",
            destination=expected_pc2["ip"],
            timeout=args.ping_timeout,
        )
        report["baseline_ping"] = baseline
        if not baseline.get("success"):
            raise ScriptBridgeError(
                f"Baseline ping did not pass; cannot inject fault: {baseline!r}"
            )

        _logged_command(
            bridge,
            audit,
            "inject_bad_mask",
            configure_host_ip_js(
                "PC1",
                "FastEthernet0",
                wrong_pc1["ip"],
                wrong_pc1["mask"],
            ),
        )
        _logged_command(bridge, audit, "fast_forward_faulted", fast_forward_js())
        time.sleep(1)
        failed_ping = _run_ping(
            bridge,
            audit,
            label="faulted_ping",
            device="PC1",
            destination=expected_pc2["ip"],
            timeout=args.ping_timeout,
        )
        report["faulted_ping"] = failed_ping

        observed = _logged_command(
            bridge,
            audit,
            "read_faulted_pc1",
            host_ip_state_js("PC1", "FastEthernet0"),
        )
        if not isinstance(observed, dict):
            raise ScriptBridgeError(f"Invalid PC1 readback: {observed!r}")
        report["faulted_address"] = observed
        diagnosis = diagnose_host_address(
            expected={
                "device": "PC1",
                "port": "FastEthernet0",
                "ip": expected_pc1["ip"],
                "mask": expected_pc1["mask"],
            },
            observed=observed,
            peer_ip=expected_pc2["ip"],
        )
        report["diagnosis"] = diagnosis.to_dict() if diagnosis else None
        audit.record(
            "diagnosis_completed",
            failed_ping=failed_ping,
            observed=observed,
            diagnosis=report["diagnosis"],
        )
        if diagnosis is None:
            raise ScriptBridgeError(
                "Ping failed but no supported deterministic diagnosis matched"
            )

        repair_supported = diagnosis.code in {
            "HOST_IP_MISMATCH",
            "HOST_MASK_MISMATCH",
        }
        if not repair_supported:
            raise ScriptBridgeError(
                f"Diagnosis {diagnosis.code} has no automatic repair rule"
            )

        repaired = _logged_command(
            bridge,
            audit,
            "repair_pc1_address",
            configure_host_ip_js(
                "PC1",
                "FastEthernet0",
                expected_pc1["ip"],
                expected_pc1["mask"],
            ),
        )
        report["repair_result"] = repaired
        audit.record(
            "repair_applied",
            diagnosis_code=diagnosis.code,
            device=diagnosis.device,
            port=diagnosis.port,
            result=repaired,
        )

        _logged_command(bridge, audit, "fast_forward_repaired", fast_forward_js())
        time.sleep(1)
        final_ping = _run_ping(
            bridge,
            audit,
            label="final_verification",
            device="PC1",
            destination=expected_pc2["ip"],
            timeout=args.ping_timeout,
        )
        report["final_ping"] = final_ping
        if not final_ping.get("success"):
            raise ScriptBridgeError(
                f"Repair did not restore connectivity: {final_ping!r}"
            )

        repaired_pc1 = _logged_command(
            bridge,
            audit,
            "verify_repaired_pc1",
            host_ip_state_js("PC1", "FastEthernet0"),
        )
        report["repaired_pc1"] = repaired_pc1
        verify_diagnosis = (
            diagnose_host_address(
                expected={
                    "device": "PC1",
                    "port": "FastEthernet0",
                    "ip": expected_pc1["ip"],
                    "mask": expected_pc1["mask"],
                },
                observed=repaired_pc1,
                peer_ip=expected_pc2["ip"],
            )
            if isinstance(repaired_pc1, dict)
            else None
        )
        if verify_diagnosis is not None:
            raise ScriptBridgeError(
                f"Repair readback still differs: {verify_diagnosis.to_dict()!r}"
            )

        if project_path.exists():
            project_path.unlink()
        _logged_command(
            bridge,
            audit,
            "save_repaired_project",
            save_project_js(project_path),
        )
        file_state: dict[str, object] = {"exists": False, "size": 0}
        deadline = time.monotonic() + args.save_timeout
        while time.monotonic() < deadline:
            state = _logged_command(
                bridge, audit, "check_repaired_file", file_size_js(project_path)
            )
            if isinstance(state, dict):
                file_state = state
            if file_state.get("exists") and int(file_state.get("size", 0)) > 0:
                break
            time.sleep(0.4)
        report["saved_file"] = file_state
        if not file_state.get("exists") or int(file_state.get("size", 0)) <= 0:
            raise ScriptBridgeError("PT did not save the repaired PKT")

        report["repair_rounds"] = 1
        report["status"] = "passed"
        audit.record(
            "verification_finished",
            status="passed",
            repair_rounds=1,
            diagnosis_code=diagnosis.code,
            final_ping_success=bool(final_ping.get("success")),
        )
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        audit.record("run_failed", status="failed", error=report["error"])
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


CLI_ERROR_RE = re.compile(
    r"%(?:\s*)(?:Invalid input|Incomplete command|Ambiguous command|"
    r"Unknown command|Unrecognized command)",
    re.IGNORECASE,
)


def _assert_cli_output(result: object, label: str) -> str:
    if not isinstance(result, dict) or not isinstance(result.get("output"), str):
        raise ScriptBridgeError(f"Invalid {label} result: {result!r}")
    output = str(result["output"])
    if CLI_ERROR_RE.search(output):
        raise ScriptBridgeError(f"{label} reported CLI errors: {output}")
    return output


def _parse_vlan_output(output: str) -> dict[str, object]:
    vlan10 = None
    vlan20 = None
    for line in output.splitlines():
        if re.match(r"\s*10\s+FINANCE\s+active\b", line, re.IGNORECASE):
            vlan10 = line.strip()
        if re.match(r"\s*20\s+GUEST\s+active\b", line, re.IGNORECASE):
            vlan20 = line.strip()
    return {
        "vlan10": vlan10,
        "vlan20": vlan20,
        "pc1_in_vlan10": bool(vlan10 and "Fa0/1" in vlan10),
        "pc2_in_vlan10": bool(vlan10 and "Fa0/2" in vlan10),
        "pc3_in_vlan20": bool(vlan20 and "Fa0/3" in vlan20),
    }


def _parse_acl_output(output: str) -> dict[str, bool]:
    normalized = output.lower()
    return {
        "deny_pc1": "deny host 192.168.10.10" in normalized,
        "permit_any": "permit any" in normalized,
    }


def _run_ios_cli(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    *,
    label: str,
    device: str,
    commands: list[str],
    timeout: float,
    prepare_boot_dialog: bool = False,
) -> dict[str, object]:
    if commands:
        safety_issues = CommandSafetyValidator().validate(commands)
        if safety_issues:
            audit.record(
                "command_blocked",
                label=label,
                device=device,
                commands=list(commands),
                issues=[issue.to_dict() for issue in safety_issues],
            )
            details = "; ".join(
                f"{issue.code}: {issue.message}"
                for issue in safety_issues
            )
            print(
                f"SECURITY BLOCK [{label}] {device}: {details}",
                file=sys.stderr,
            )
            raise CommandSafetyError(details)
    state = _logged_read(
        bridge,
        audit,
        f"{label}_terminal_state",
        terminal_state_js(device),
        timeout=min(timeout, 12.0),
    )
    prompt = str(state.get("prompt", ""))

    if prepare_boot_dialog and "initial configuration dialog" in prompt.lower():
        _logged_command(
            bridge,
            audit,
            f"{label}_dismiss_initial_config",
            enter_ios_command_js(
                device,
                "no",
                trusted_control=True,
            ),
            timeout=timeout,
        )
        time.sleep(0.8)
        state = _logged_read(
            bridge,
            audit,
            f"{label}_terminal_after_initial_config",
            terminal_state_js(device),
            timeout=min(timeout, 12.0),
        )
        prompt = str(state.get("prompt", ""))

    if prepare_boot_dialog and not prompt:
        _logged_command(
            bridge,
            audit,
            f"{label}_continue_boot",
            enter_ios_command_js(
                device,
                "",
                trusted_control=True,
            ),
            timeout=timeout,
        )
        time.sleep(0.8)
        state = _logged_read(
            bridge,
            audit,
            f"{label}_terminal_after_boot",
            terminal_state_js(device),
            timeout=min(timeout, 12.0),
        )
        prompt = str(state.get("prompt", ""))

    if prompt.endswith(">"):
        _logged_command(
            bridge,
            audit,
            f"{label}_input_warmup",
            enter_ios_command_js(device, "show clock"),
            timeout=timeout,
        )
        time.sleep(0.4)
        _logged_command(
            bridge,
            audit,
            f"{label}_enable",
            enter_ios_command_js(device, "enable"),
            timeout=timeout,
        )
        time.sleep(0.8)
        state = _logged_read(
            bridge,
            audit,
            f"{label}_terminal_after_enable",
            terminal_state_js(device),
            timeout=min(timeout, 12.0),
        )
        prompt = str(state.get("prompt", ""))

    if not prompt.endswith("#"):
        raise ScriptBridgeError(
            f"{label} could not enter privileged mode; prompt={prompt!r}"
        )

    if not commands:
        return {"commands": [], "output": "", "prompts": []}
    _logged_command(
        bridge,
        audit,
        f"{label}_input_warmup",
        enter_ios_command_js(device, "show clock"),
        timeout=timeout,
    )
    time.sleep(0.4)
    output_start: int | None = None
    prompts: list[dict[str, str]] = []
    for index, command in enumerate(commands, start=1):
        dispatch = _logged_command(
            bridge,
            audit,
            f"{label}_{index:02d}_enter",
            enter_ios_command_js(device, command),
            timeout=timeout,
        )
        if not isinstance(dispatch, dict) or "outputStart" not in dispatch:
            raise ScriptBridgeError(
                f"Invalid CLI dispatch for {command!r}: {dispatch!r}"
            )
        if output_start is None:
            output_start = int(dispatch["outputStart"])
        prompts.append(
            {
                "command": command,
                "after": str(dispatch.get("prompt", "")),
            }
        )
        time.sleep(0.25)
    assert output_start is not None
    time.sleep(0.35)
    readback = _logged_read(
        bridge,
        audit,
        f"{label}_output",
        read_command_output_js(device, output_start),
        timeout=min(timeout, 12.0),
    )
    part = readback.get("output") if isinstance(readback, dict) else None
    if not isinstance(part, str):
        raise ScriptBridgeError(f"Invalid CLI readback: {readback!r}")
    if CLI_ERROR_RE.search(part):
        raise ScriptBridgeError(
            f"{label} reported a CLI error: {part}"
        )
    return {
        "commands": commands,
        "output": part,
        "prompts": prompts,
    }


def _save_and_wait(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    project_path: Path,
    timeout: float,
) -> dict[str, object]:
    if project_path.exists():
        project_path.unlink()
    _logged_command(
        bridge, audit, f"save_{project_path.stem}", save_project_js(project_path)
    )
    deadline = time.monotonic() + timeout
    state: dict[str, object] = {"exists": False, "size": 0}
    while time.monotonic() < deadline:
        candidate = _logged_command(
            bridge,
            audit,
            f"check_{project_path.stem}",
            file_size_js(project_path),
        )
        if isinstance(candidate, dict):
            state = candidate
        if state.get("exists") and int(state.get("size", 0)) > 0:
            return state
        time.sleep(0.4)
    raise ScriptBridgeError(
        f"PT did not save {project_path}; last state={state!r}"
    )


def command_config_suite_demo(args: argparse.Namespace) -> int:
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    vlan_path = (artifacts / "config-vlan-smoke.pkt").resolve()
    acl_path = (artifacts / "config-acl-smoke.pkt").resolve()
    report_path = (artifacts / "config-suite-smoke.json").resolve()
    audit_path = (artifacts / "config-suite-audit.jsonl").resolve()

    run_id = f"config-suite-{uuid.uuid4().hex[:12]}"
    audit = JsonlAuditLogger(audit_path, run_id)
    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "run_id": run_id,
        "status": "starting",
        "vlan_project": str(vlan_path),
        "acl_project": str(acl_path),
        "audit_path": str(audit_path),
    }
    audit.record("run_started", intent="configuration suite")

    try:
        bridge.start()
        audit.record("bridge_started", url=f"http://127.0.0.1:{bridge.port}")
        bridge.wait_for_extension(timeout=args.connect_timeout)
        audit.record("extension_connected", status=bridge.status())

        # VLAN access assignment and isolation.
        _logged_command(bridge, audit, "vlan_new_project", new_project_js())
        vlan_topology = _logged_command(
            bridge, audit, "vlan_topology", vlan_topology_js()
        )
        _logged_command(bridge, audit, "vlan_fast_forward", fast_forward_js())
        time.sleep(1)
        vlan_applied = _logged_command(
            bridge,
            audit,
            "vlan_configure_switch_api",
            configure_switch_vlans_js(
                "SW1",
                {10: "FINANCE", 20: "GUEST"},
                {
                    "FastEthernet0/1": 10,
                    "FastEthernet0/2": 10,
                    "FastEthernet0/3": 20,
                },
            ),
        )
        vlan_state = _logged_command(
            bridge,
            audit,
            "vlan_state_after_apply",
            switch_vlan_state_js(
                "SW1",
                ["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"],
            ),
        )

        _logged_command(
            bridge,
            audit,
            "vlan_configure_pc1",
            configure_host_ip_js(
                "PC1", "FastEthernet0", "192.168.10.10", "255.255.255.0"
            ),
        )
        _logged_command(
            bridge,
            audit,
            "vlan_configure_pc2",
            configure_host_ip_js(
                "PC2", "FastEthernet0", "192.168.10.11", "255.255.255.0"
            ),
        )
        _logged_command(
            bridge,
            audit,
            "vlan_configure_pc3",
            configure_host_ip_js(
                "PC3", "FastEthernet0", "192.168.20.20", "255.255.255.0"
            ),
        )
        _logged_command(bridge, audit, "vlan_fast_forward_after_ip", fast_forward_js())
        time.sleep(1)

        _run_ping(
            bridge,
            audit,
            label="vlan_pc1_pc2_warmup",
            device="PC1",
            destination="192.168.10.11",
            timeout=args.ping_timeout,
        )
        vlan_same = _run_ping(
            bridge,
            audit,
            label="vlan_pc1_pc2_verify",
            device="PC1",
            destination="192.168.10.11",
            timeout=args.ping_timeout,
        )
        vlan_cross = _run_ping(
            bridge,
            audit,
            label="vlan_pc1_pc3_isolated",
            device="PC1",
            destination="192.168.20.20",
            timeout=args.ping_timeout,
        )
        vlan_ids = {
            int(vlan["id"]): str(vlan["name"])
            for vlan in vlan_state.get("vlans", [])
            if isinstance(vlan, dict) and "id" in vlan
        }
        vlan_ports = vlan_state.get("ports", {})
        vlan_passed = (
            vlan_ids.get(10) == "FINANCE"
            and vlan_ids.get(20) == "GUEST"
            and vlan_ports.get("FastEthernet0/1", {}).get("vlan") == 10
            and vlan_ports.get("FastEthernet0/2", {}).get("vlan") == 10
            and vlan_ports.get("FastEthernet0/3", {}).get("vlan") == 20
            and bool(vlan_same.get("success"))
            and not bool(vlan_cross.get("success"))
        )
        vlan_saved = _save_and_wait(
            bridge, audit, vlan_path, args.save_timeout
        )
        _logged_command(bridge, audit, "vlan_new_for_reopen", new_project_js())
        _logged_command(
            bridge, audit, "vlan_reopen", open_project_js(vlan_path)
        )
        _logged_command(bridge, audit, "vlan_reopen_fast_forward", fast_forward_js())
        time.sleep(1)
        vlan_after_state = _logged_command(
            bridge,
            audit,
            "vlan_state_after_reopen",
            switch_vlan_state_js(
                "SW1",
                ["FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"],
            ),
        )
        after_vlan_ids = {
            int(vlan["id"]): str(vlan["name"])
            for vlan in vlan_after_state.get("vlans", [])
            if isinstance(vlan, dict) and "id" in vlan
        }
        after_vlan_ports = vlan_after_state.get("ports", {})
        vlan_passed = vlan_passed and all(
            (
                after_vlan_ids.get(10) == "FINANCE",
                after_vlan_ids.get(20) == "GUEST",
                after_vlan_ports.get("FastEthernet0/1", {}).get("vlan") == 10,
                after_vlan_ports.get("FastEthernet0/2", {}).get("vlan") == 10,
                after_vlan_ports.get("FastEthernet0/3", {}).get("vlan") == 20,
            )
        )
        report["vlan"] = {
            "status": "passed" if vlan_passed else "failed",
            "topology": vlan_topology,
            "generated_commands": vlan_switch_config_commands(),
            "applied": vlan_applied,
            "state_after_apply": vlan_state,
            "same_vlan_ping": vlan_same,
            "cross_vlan_ping": vlan_cross,
            "state_after_reopen": vlan_after_state,
            "saved_file": vlan_saved,
        }
        audit.record("vlan_verification_finished", **report["vlan"])
        if not vlan_passed:
            raise ScriptBridgeError(f"VLAN verification failed: {report['vlan']!r}")

        # Routed interfaces and ACL enforcement.
        _logged_command(bridge, audit, "acl_new_project", new_project_js())
        acl_topology = _logged_command(
            bridge, audit, "acl_topology", acl_topology_js()
        )
        _logged_command(bridge, audit, "acl_fast_forward", fast_forward_js())
        time.sleep(1)
        router_applied = _logged_command(
            bridge,
            audit,
            "acl_configure_router_api",
            configure_router_ipv4_js(
                "R1",
                {
                    "GigabitEthernet0/0": {
                        "ip": "192.168.10.1",
                        "mask": "255.255.255.0",
                    },
                    "GigabitEthernet0/1": {
                        "ip": "192.168.20.1",
                        "mask": "255.255.255.0",
                    },
                },
            ),
        )
        router_state = _logged_command(
            bridge,
            audit,
            "acl_router_state_after_apply",
            router_ipv4_state_js(
                "R1", ["GigabitEthernet0/0", "GigabitEthernet0/1"]
            ),
        )

        _logged_command(
            bridge,
            audit,
            "acl_configure_pc1",
            configure_host_ip_js(
                "PC1",
                "FastEthernet0",
                "192.168.10.10",
                "255.255.255.0",
                "192.168.10.1",
            ),
        )
        _logged_command(
            bridge,
            audit,
            "acl_configure_pc2",
            configure_host_ip_js(
                "PC2",
                "FastEthernet0",
                "192.168.20.20",
                "255.255.255.0",
                "192.168.20.1",
            ),
        )
        _logged_command(
            bridge, audit, "acl_fast_forward_baseline", fast_forward_js()
        )
        time.sleep(1)
        _run_ping(
            bridge,
            audit,
            label="acl_baseline_warmup",
            device="PC1",
            destination="192.168.20.20",
            timeout=args.ping_timeout,
        )
        acl_baseline = _run_ping(
            bridge,
            audit,
            label="acl_baseline_verify",
            device="PC1",
            destination="192.168.20.20",
            timeout=args.ping_timeout,
        )
        if not acl_baseline.get("success"):
            raise ScriptBridgeError(
                f"Routed baseline ping failed before ACL: {acl_baseline!r}"
            )

        acl_applied = _logged_command(
            bridge,
            audit,
            "acl_apply_api",
            configure_acl_js(
                "R1",
                "10",
                ["deny host 192.168.10.10", "permit any"],
                "GigabitEthernet0/1",
            ),
        )
        acl_state = _logged_command(
            bridge,
            audit,
            "acl_state_after_apply",
            acl_state_js("R1", "10", "GigabitEthernet0/1"),
        )
        _logged_command(bridge, audit, "acl_fast_forward_faulted", fast_forward_js())
        time.sleep(1)
        acl_denied = _run_ping(
            bridge,
            audit,
            label="acl_denied_ping",
            device="PC1",
            destination="192.168.20.20",
            timeout=args.ping_timeout,
        )
        acl_saved = _save_and_wait(
            bridge, audit, acl_path, args.save_timeout
        )
        _logged_command(bridge, audit, "acl_new_for_reopen", new_project_js())
        _logged_command(
            bridge, audit, "acl_reopen", open_project_js(acl_path)
        )
        _logged_command(bridge, audit, "acl_reopen_fast_forward", fast_forward_js())
        time.sleep(1)
        acl_after_state = _logged_command(
            bridge,
            audit,
            "acl_state_after_reopen",
            acl_state_js("R1", "10", "GigabitEthernet0/1"),
        )
        router_after_state = _logged_command(
            bridge,
            audit,
            "acl_router_state_after_reopen",
            router_ipv4_state_js(
                "R1", ["GigabitEthernet0/0", "GigabitEthernet0/1"]
            ),
        )
        acl_rules = " | ".join(
            str(item) for item in acl_state.get("commands", [])
        ).lower()
        acl_after_rules = " | ".join(
            str(item) for item in acl_after_state.get("commands", [])
        ).lower()
        acl_passed = (
            "deny host 192.168.10.10" in acl_rules
            and "permit any" in acl_rules
            and acl_state.get("aclOut") == "10"
            and "deny host 192.168.10.10" in acl_after_rules
            and "permit any" in acl_after_rules
            and acl_after_state.get("aclOut") == "10"
            and not bool(acl_denied.get("success"))
        )
        report["acl"] = {
            "status": "passed" if acl_passed else "failed",
            "topology": acl_topology,
            "generated_router_commands": acl_router_config_commands(),
            "generated_acl_commands": acl_apply_commands(),
            "router_applied": router_applied,
            "router_state": router_state,
            "acl_applied": acl_applied,
            "baseline_ping": acl_baseline,
            "acl_state": acl_state,
            "denied_ping": acl_denied,
            "acl_state_after_reopen": acl_after_state,
            "router_state_after_reopen": router_after_state,
            "saved_file": acl_saved,
        }
        audit.record("acl_verification_finished", **report["acl"])
        if not acl_passed:
            raise ScriptBridgeError(f"ACL verification failed: {report['acl']!r}")

        report["status"] = "passed"
        audit.record(
            "suite_verification_finished",
            status="passed",
            vlan_status="passed",
            acl_status="passed",
        )
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        audit.record("run_failed", status="failed", error=report["error"])
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


def _configure_routed_test_topology(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    prefix: str,
) -> dict[str, object]:
    _logged_command(bridge, audit, f"{prefix}_new_project", new_project_js())
    topology = _logged_command(
        bridge,
        audit,
        f"{prefix}_topology",
        routed_two_router_topology_js(),
    )
    _logged_command(bridge, audit, f"{prefix}_fast_forward", fast_forward_js())
    time.sleep(1)
    _logged_command(
        bridge,
        audit,
        f"{prefix}_r1_interfaces",
        configure_router_ipv4_js(
            "R1",
            {
                "GigabitEthernet0/0": {
                    "ip": "172.16.10.1",
                    "mask": "255.255.255.0",
                },
                "GigabitEthernet0/1": {
                    "ip": "10.0.0.1",
                    "mask": "255.255.255.252",
                },
            },
        ),
    )
    _logged_command(
        bridge,
        audit,
        f"{prefix}_r2_interfaces",
        configure_router_ipv4_js(
            "R2",
            {
                "GigabitEthernet0/0": {
                    "ip": "172.16.20.1",
                    "mask": "255.255.255.0",
                },
                "GigabitEthernet0/1": {
                    "ip": "10.0.0.2",
                    "mask": "255.255.255.252",
                },
            },
        ),
    )
    _logged_command(
        bridge,
        audit,
        f"{prefix}_pc1",
        configure_host_ip_js(
            "PC1",
            "FastEthernet0",
            "172.16.10.10",
            "255.255.255.0",
            "172.16.10.1",
        ),
    )
    _logged_command(
        bridge,
        audit,
        f"{prefix}_pc2",
        configure_host_ip_js(
            "PC2",
            "FastEthernet0",
            "172.16.20.20",
            "255.255.255.0",
            "172.16.20.1",
        ),
    )
    _logged_command(
        bridge, audit, f"{prefix}_fast_forward_after_ip", fast_forward_js()
    )
    time.sleep(1)
    _run_ios_cli(
        bridge,
        audit,
        label=f"{prefix}_prepare_r1_cli",
        device="R1",
        commands=[],
        timeout=30.0,
        prepare_boot_dialog=True,
    )
    _run_ios_cli(
        bridge,
        audit,
        label=f"{prefix}_prepare_r2_cli",
        device="R2",
        commands=[],
        timeout=30.0,
        prepare_boot_dialog=True,
    )
    return {
        "topology": topology,
        "r1": _logged_command(
            bridge,
            audit,
            f"{prefix}_r1_state",
            router_ipv4_state_js(
                "R1", ["GigabitEthernet0/0", "GigabitEthernet0/1"]
            ),
        ),
        "r2": _logged_command(
            bridge,
            audit,
            f"{prefix}_r2_state",
            router_ipv4_state_js(
                "R2", ["GigabitEthernet0/0", "GigabitEthernet0/1"]
            ),
        ),
    }


def _routing_state(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    label: str,
    devices: tuple[str, ...] = ("R1", "R2"),
) -> dict[str, object]:
    return {
        device: _logged_command(
            bridge,
            audit,
            f"{label}_{device.lower()}",
            routing_state_js(device),
        )
        for device in devices
    }


def _prepare_reopened_routers(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    prefix: str,
) -> None:
    for device in ("R1", "R2"):
        _run_ios_cli(
            bridge,
            audit,
            label=f"{prefix}_prepare_{device.lower()}",
            device=device,
            commands=[],
            timeout=30.0,
            prepare_boot_dialog=True,
        )


def _run_dsl_verification(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    network: CompiledNetwork,
    *,
    label: str,
    ping_timeout: float,
    specs: tuple[VerificationSpec, ...] | None = None,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    selected = network.verification if specs is None else specs
    for index, spec in enumerate(selected, start=1):
        address = (
            destination_ipv6(network, spec.destination)
            if spec.protocol == "ping6"
            else destination_ip(network, spec.destination)
        )
        if spec.expected == "pass":
            _run_ping(
                bridge,
                audit,
                label=f"{label}_{index:02d}_warmup",
                device=spec.source,
                destination=address,
                timeout=ping_timeout,
            )
        ping = _run_ping(
            bridge,
            audit,
            label=f"{label}_{index:02d}_verify",
            device=spec.source,
            destination=address,
            timeout=ping_timeout,
        )
        result = evaluate_verification(spec, ping, address)
        results.append(result.to_dict())
    return results


def _run_dsl_advanced_verification(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    network: CompiledNetwork,
    *,
    label: str,
    traceroute_timeout: float,
    route_assertions: tuple[RouteAssertionSpec, ...] | None = None,
    traceroutes: tuple[TracerouteSpec, ...] | None = None,
) -> dict[str, object]:
    route_cache: dict[str, object] = {}
    route_results: list[dict[str, object]] = []
    selected_routes = (
        network.route_assertions
        if route_assertions is None
        else route_assertions
    )
    for index, spec in enumerate(selected_routes, start=1):
        if spec.device not in route_cache:
            route_cache[spec.device] = _logged_command(
                bridge,
                audit,
                f"{label}_route_state_{spec.device}",
                routing_state_js(spec.device),
            )
        result = evaluate_route_assertion(
            spec,
            route_cache[spec.device],
        )
        route_results.append(result.to_dict())

    traceroute_results: list[dict[str, object]] = []
    selected_traces = (
        network.traceroutes if traceroutes is None else traceroutes
    )
    for index, spec in enumerate(selected_traces, start=1):
        address = destination_ip(network, spec.destination)
        trace = _run_traceroute(
            bridge,
            audit,
            label=f"{label}_traceroute_{index:02d}",
            device=spec.source,
            destination=address,
            timeout=traceroute_timeout,
        )
        result = evaluate_traceroute(
            spec,
            str(trace["raw_output"]),
        )
        traceroute_results.append(result.to_dict())
    return {
        "route_assertions": route_results,
        "traceroutes": traceroute_results,
    }


def _wait_for_protocol_convergence(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    prefix: str,
    *,
    rounds: int = 3,
) -> None:
    for index in range(rounds):
        _logged_command(
            bridge,
            audit,
            f"{prefix}_fast_forward_{index + 1}",
            fast_forward_js(),
        )
        time.sleep(0.75)


def _collect_dsl_dhcp_leases(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    network: CompiledNetwork,
    *,
    attempts: int = 2,
) -> list[object]:
    leases: list[object] = []
    for attempt in range(1, attempts + 1):
        leases = []
        for item in network.dhcp_clients:
            leases.append(
                _logged_command(
                    bridge,
                    audit,
                    f"dsl_dhcp_lease_{item.device}_round_{attempt}",
                    host_ip_state_js(item.device, item.port),
                )
            )
        if _dhcp_leases_are_valid(leases, network.dhcp_networks):
            return leases
        for item, lease in zip(network.dhcp_clients, leases):
            if _dhcp_leases_are_valid(
                [lease],
                network.dhcp_networks,
            ):
                continue
            _logged_command(
                bridge,
                audit,
                f"dsl_dhcp_retry_{item.device}_round_{attempt}",
                configure_dhcp_client_js(item.device, item.port),
            )
        _wait_for_protocol_convergence(
            bridge,
            audit,
            f"dsl_dhcp_wait_{attempt}",
            rounds=3,
        )
    return leases


def command_routing_suite_demo(args: argparse.Namespace) -> int:
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    static_path = (artifacts / "config-static-routing.pkt").resolve()
    rip_path = (artifacts / "config-rip-v1-v2.pkt").resolve()
    ospf_path = (artifacts / "config-ospf.pkt").resolve()
    report_path = (artifacts / "config-routing-suite.json").resolve()
    audit_path = (artifacts / "config-routing-audit.jsonl").resolve()

    run_id = f"routing-suite-{uuid.uuid4().hex[:12]}"
    audit = JsonlAuditLogger(audit_path, run_id)
    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "run_id": run_id,
        "status": "starting",
        "audit_path": str(audit_path),
        "projects": {
            "static": str(static_path),
            "rip": str(rip_path),
            "ospf": str(ospf_path),
        },
    }
    audit.record("run_started", intent="routing configuration suite")

    try:
        bridge.start()
        bridge.wait_for_extension(timeout=args.connect_timeout)
        audit.record("extension_connected", status=bridge.status())

        static_topology = _configure_routed_test_topology(
            bridge, audit, "static"
        )
        static_r1 = _logged_command(
            bridge,
            audit,
            "static_default_route",
            configure_static_routes_js(
                "R1",
                [
                    {
                        "network": "0.0.0.0",
                        "mask": "0.0.0.0",
                        "nextHop": "10.0.0.2",
                        "port": "GigabitEthernet0/1",
                        "admin_distance": 1,
                    }
                ],
            ),
        )
        static_r2 = _logged_command(
            bridge,
            audit,
            "static_return_route",
            configure_static_routes_js(
                "R2",
                [
                    {
                        "network": "172.16.10.0",
                        "mask": "255.255.255.0",
                        "nextHop": "10.0.0.1",
                        "port": "GigabitEthernet0/1",
                        "admin_distance": 1,
                    }
                ],
            ),
        )
        _wait_for_protocol_convergence(bridge, audit, "static")
        static_state = _routing_state(bridge, audit, "static_routes")
        _run_ping(
            bridge,
            audit,
            label="static_warmup",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        static_ping = _run_ping(
            bridge,
            audit,
            label="static_verify",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        static_saved = _save_and_wait(
            bridge, audit, static_path, args.save_timeout
        )
        _logged_command(
            bridge, audit, "static_new_for_reopen", new_project_js()
        )
        _logged_command(
            bridge,
            audit,
            "static_reopen",
            open_project_js(static_path),
        )
        _prepare_reopened_routers(bridge, audit, "static_reopen")
        _wait_for_protocol_convergence(
            bridge, audit, "static_reopen", rounds=1
        )
        static_after = _routing_state(
            bridge, audit, "static_routes_after_reopen"
        )
        _run_ping(
            bridge,
            audit,
            label="static_warmup_after_reopen",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        static_ping_after = _run_ping(
            bridge,
            audit,
            label="static_verify_after_reopen",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        static_passed = (
            all(
                item.get("ok")
                for item in static_r1.get("added", [])
                + static_r2.get("added", [])
            )
            and bool(static_ping.get("success"))
            and bool(static_ping_after.get("success"))
            and any(
                route.get("network") == "0.0.0.0"
                and route.get("mask") == "0.0.0.0"
                for route in static_state["R1"].get("staticRoutes", [])
            )
            and any(
                route.get("network") == "172.16.10.0"
                for route in static_state["R2"].get("staticRoutes", [])
            )
            and any(
                route.get("network") == "0.0.0.0"
                for route in static_after["R1"].get("staticRoutes", [])
            )
        )
        report["static"] = {
            "status": "passed" if static_passed else "failed",
            "topology": static_topology,
            "routes": {"R1": static_r1, "R2": static_r2},
            "state": static_state,
            "ping": static_ping,
            "state_after_reopen": static_after,
            "ping_after_reopen": static_ping_after,
            "saved_file": static_saved,
        }
        audit.record("static_verification_finished", **report["static"])
        if not static_passed:
            raise ScriptBridgeError(
                f"Static routing verification failed: {report['static']!r}"
            )

        rip_topology = _configure_routed_test_topology(bridge, audit, "rip")
        rip_v1_r1 = _run_ios_cli(
            bridge,
            audit,
            label="rip_v1_r1",
            device="R1",
            commands=rip_config_commands(1, auto_summary=True),
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        rip_v1_r2 = _run_ios_cli(
            bridge,
            audit,
            label="rip_v1_r2",
            device="R2",
            commands=rip_config_commands(1, auto_summary=True),
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        _wait_for_protocol_convergence(bridge, audit, "rip_v1")
        rip_v1_state = _routing_state(bridge, audit, "rip_v1_routes")
        _run_ping(
            bridge,
            audit,
            label="rip_v1_warmup",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        rip_v1_ping = _run_ping(
            bridge,
            audit,
            label="rip_v1_ping",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        rip_v1_show = _run_ios_cli(
            bridge,
            audit,
            label="rip_v1_show_config",
            device="R1",
            commands=show_rip_config_commands(),
            timeout=args.cli_timeout,
        )

        rip_v2_r1 = _run_ios_cli(
            bridge,
            audit,
            label="rip_v2_r1",
            device="R1",
            commands=rip_config_commands(2, auto_summary=False),
            timeout=args.cli_timeout,
        )
        rip_v2_r2 = _run_ios_cli(
            bridge,
            audit,
            label="rip_v2_r2",
            device="R2",
            commands=rip_config_commands(2, auto_summary=False),
            timeout=args.cli_timeout,
        )
        _wait_for_protocol_convergence(bridge, audit, "rip_v2")
        rip_v2_state = _routing_state(bridge, audit, "rip_v2_routes")
        _run_ping(
            bridge,
            audit,
            label="rip_v2_warmup",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        rip_v2_ping = _run_ping(
            bridge,
            audit,
            label="rip_v2_ping",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        rip_v2_show = _run_ios_cli(
            bridge,
            audit,
            label="rip_v2_show_config",
            device="R1",
            commands=show_rip_config_commands(),
            timeout=args.cli_timeout,
        )
        rip_saved = _save_and_wait(bridge, audit, rip_path, args.save_timeout)
        _logged_command(bridge, audit, "rip_new_for_reopen", new_project_js())
        _logged_command(bridge, audit, "rip_reopen", open_project_js(rip_path))
        _prepare_reopened_routers(bridge, audit, "rip_reopen")
        _wait_for_protocol_convergence(
            bridge, audit, "rip_reopen", rounds=1
        )
        rip_after_state = _routing_state(
            bridge, audit, "rip_routes_after_reopen"
        )
        rip_after_show = _run_ios_cli(
            bridge,
            audit,
            label="rip_show_after_reopen",
            device="R1",
            commands=show_rip_config_commands(),
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        _run_ping(
            bridge,
            audit,
            label="rip_warmup_after_reopen",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        rip_after_ping = _run_ping(
            bridge,
            audit,
            label="rip_verify_after_reopen",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        rip_v2_config = str(rip_v2_show.get("output", "")).lower()
        rip_after_config = str(rip_after_show.get("output", "")).lower()
        rip_passed = (
            "version 1" in str(rip_v1_show.get("output", "")).lower()
            and "version 2" in rip_v2_config
            and "no auto-summary" in rip_v2_config
            and "network 172.16.0.0" in rip_v2_config
            and bool(rip_v2_ping.get("success"))
            and "version 2" in rip_after_config
            and "no auto-summary" in rip_after_config
            and bool(rip_after_ping.get("success"))
        )
        report["rip"] = {
            "status": "passed" if rip_passed else "failed",
            "topology": rip_topology,
            "v1": {
                "outputs": {"R1": rip_v1_r1, "R2": rip_v1_r2},
                "state": rip_v1_state,
                "ping": rip_v1_ping,
                "show_config": rip_v1_show,
            },
            "v2": {
                "outputs": {"R1": rip_v2_r1, "R2": rip_v2_r2},
                "state": rip_v2_state,
                "ping": rip_v2_ping,
                "show_config": rip_v2_show,
            },
            "after_reopen": {
                "state": rip_after_state,
                "show_config": rip_after_show,
                "ping": rip_after_ping,
            },
            "saved_file": rip_saved,
        }
        audit.record("rip_verification_finished", **report["rip"])
        if not rip_passed:
            raise ScriptBridgeError(
                f"RIP verification failed: {report['rip']!r}"
            )

        ospf_topology = _configure_routed_test_topology(bridge, audit, "ospf")
        ospf_r1 = _run_ios_cli(
            bridge,
            audit,
            label="ospf_r1",
            device="R1",
            commands=ospf_config_commands(
                100,
                networks=(
                    ("172.16.10.0", "0.0.0.255", "0"),
                    ("10.0.0.0", "0.0.0.3", "0"),
                ),
            ),
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        ospf_r2 = _run_ios_cli(
            bridge,
            audit,
            label="ospf_r2",
            device="R2",
            commands=ospf_config_commands(
                100,
                networks=(
                    ("172.16.20.0", "0.0.0.255", "0"),
                    ("10.0.0.0", "0.0.0.3", "0"),
                ),
            ),
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        _wait_for_protocol_convergence(bridge, audit, "ospf", rounds=4)
        ospf_state = _routing_state(bridge, audit, "ospf_routes")
        ospf_show = _run_ios_cli(
            bridge,
            audit,
            label="ospf_show_config",
            device="R1",
            commands=show_ospf_config_commands(),
            timeout=args.cli_timeout,
        )
        _run_ping(
            bridge,
            audit,
            label="ospf_warmup",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        ospf_ping = _run_ping(
            bridge,
            audit,
            label="ospf_ping",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        ospf_saved = _save_and_wait(bridge, audit, ospf_path, args.save_timeout)
        _logged_command(
            bridge, audit, "ospf_new_for_reopen", new_project_js()
        )
        _logged_command(
            bridge, audit, "ospf_reopen", open_project_js(ospf_path)
        )
        _prepare_reopened_routers(bridge, audit, "ospf_reopen")
        _wait_for_protocol_convergence(
            bridge, audit, "ospf_reopen", rounds=2
        )
        ospf_after_state = _routing_state(
            bridge, audit, "ospf_routes_after_reopen"
        )
        ospf_after_show = _run_ios_cli(
            bridge,
            audit,
            label="ospf_show_after_reopen",
            device="R1",
            commands=show_ospf_config_commands(),
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        _run_ping(
            bridge,
            audit,
            label="ospf_warmup_after_reopen",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        ospf_after_ping = _run_ping(
            bridge,
            audit,
            label="ospf_verify_after_reopen",
            device="PC1",
            destination="172.16.20.20",
            timeout=args.ping_timeout,
        )
        ospf_config = str(ospf_show.get("output", "")).lower()
        ospf_after_config = str(ospf_after_show.get("output", "")).lower()
        ospf_passed = (
            "router ospf 100" in ospf_config
            and "network 172.16.10.0 0.0.0.255 area 0" in ospf_config
            and "network 10.0.0.0 0.0.0.3 area 0" in ospf_config
            and bool(ospf_ping.get("success"))
            and "router ospf 100" in ospf_after_config
            and "network 172.16.10.0 0.0.0.255 area 0"
            in ospf_after_config
            and bool(ospf_after_ping.get("success"))
        )
        report["ospf"] = {
            "status": "passed" if ospf_passed else "failed",
            "topology": ospf_topology,
            "outputs": {"R1": ospf_r1, "R2": ospf_r2},
            "state": ospf_state,
            "show_config": ospf_show,
            "ping": ospf_ping,
            "after_reopen": {
                "state": ospf_after_state,
                "show_config": ospf_after_show,
                "ping": ospf_after_ping,
            },
            "saved_file": ospf_saved,
        }
        audit.record("ospf_verification_finished", **report["ospf"])
        if not ospf_passed:
            raise ScriptBridgeError(
                f"OSPF verification failed: {report['ospf']!r}"
            )

        report["status"] = "passed"
        audit.record("suite_verification_finished", status="passed")
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        audit.record("run_failed", status="failed", error=report["error"])
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


def command_trunk_suite_demo(args: argparse.Namespace) -> int:
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    project_path = (artifacts / "config-trunk.pkt").resolve()
    report_path = (artifacts / "config-trunk-suite.json").resolve()
    audit_path = (artifacts / "config-trunk-audit.jsonl").resolve()
    run_id = f"trunk-suite-{uuid.uuid4().hex[:12]}"
    audit = JsonlAuditLogger(audit_path, run_id)
    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "run_id": run_id,
        "status": "starting",
        "project": str(project_path),
        "audit_path": str(audit_path),
    }
    audit.record("run_started", intent="trunk switching suite")

    try:
        bridge.start()
        bridge.wait_for_extension(timeout=args.connect_timeout)
        _logged_command(bridge, audit, "trunk_new_project", new_project_js())
        topology = _logged_command(
            bridge, audit, "trunk_topology", trunk_topology_js()
        )
        _logged_command(bridge, audit, "trunk_fast_forward", fast_forward_js())
        time.sleep(1)
        sw1_vlans = _logged_command(
            bridge,
            audit,
            "trunk_sw1_vlans",
            configure_switch_vlans_js(
                "SW1",
                {10: "FINANCE", 20: "GUEST"},
                {"FastEthernet0/1": 10},
            ),
        )
        sw2_vlans = _logged_command(
            bridge,
            audit,
            "trunk_sw2_vlans",
            configure_switch_vlans_js(
                "SW2",
                {10: "FINANCE", 20: "GUEST"},
                {"FastEthernet0/1": 10, "FastEthernet0/2": 20},
            ),
        )
        sw1_trunk = _logged_command(
            bridge,
            audit,
            "trunk_sw1_port",
            configure_trunk_port_js("SW1", "GigabitEthernet0/1"),
        )
        sw2_trunk = _logged_command(
            bridge,
            audit,
            "trunk_sw2_port",
            configure_trunk_port_js("SW2", "GigabitEthernet0/1"),
        )
        sw1_state = _logged_command(
            bridge,
            audit,
            "trunk_sw1_state",
            switch_vlan_state_js(
                "SW1", ["FastEthernet0/1", "GigabitEthernet0/1"]
            ),
        )
        sw2_state = _logged_command(
            bridge,
            audit,
            "trunk_sw2_state",
            switch_vlan_state_js(
                "SW2",
                [
                    "FastEthernet0/1",
                    "FastEthernet0/2",
                    "GigabitEthernet0/1",
                ],
            ),
        )
        trunk_states = {
            "SW1": _logged_command(
                bridge,
                audit,
                "trunk_sw1_trunk_state",
                trunk_port_state_js("SW1", "GigabitEthernet0/1"),
            ),
            "SW2": _logged_command(
                bridge,
                audit,
                "trunk_sw2_trunk_state",
                trunk_port_state_js("SW2", "GigabitEthernet0/1"),
            ),
        }
        for device, ip in (
            ("PC1", "192.168.10.10"),
            ("PC2", "192.168.10.11"),
            ("PC3", "192.168.20.20"),
        ):
            _logged_command(
                bridge,
                audit,
                f"trunk_{device.lower()}_ip",
                configure_host_ip_js(
                    device, "FastEthernet0", ip, "255.255.255.0"
                ),
            )
        _logged_command(
            bridge, audit, "trunk_fast_forward_after_ip", fast_forward_js()
        )
        time.sleep(1)
        _run_ping(
            bridge,
            audit,
            label="trunk_same_vlan_warmup",
            device="PC1",
            destination="192.168.10.11",
            timeout=args.ping_timeout,
        )
        same_vlan = _run_ping(
            bridge,
            audit,
            label="trunk_same_vlan_verify",
            device="PC1",
            destination="192.168.10.11",
            timeout=args.ping_timeout,
        )
        cross_vlan = _run_ping(
            bridge,
            audit,
            label="trunk_cross_vlan_isolated",
            device="PC1",
            destination="192.168.20.20",
            timeout=args.ping_timeout,
        )
        sw1_show = _run_ios_cli(
            bridge,
            audit,
            label="trunk_sw1_show",
            device="SW1",
            commands=["show interfaces trunk"],
            timeout=args.cli_timeout,
            prepare_boot_dialog=True,
        )
        saved = _save_and_wait(bridge, audit, project_path, args.save_timeout)
        _logged_command(bridge, audit, "trunk_new_for_reopen", new_project_js())
        _logged_command(
            bridge, audit, "trunk_reopen", open_project_js(project_path)
        )
        _logged_command(bridge, audit, "trunk_reopen_fast_forward", fast_forward_js())
        time.sleep(1)
        after_states = {
            "SW1": _logged_command(
                bridge,
                audit,
                "trunk_sw1_state_after_reopen",
                switch_vlan_state_js(
                    "SW1", ["FastEthernet0/1", "GigabitEthernet0/1"]
                ),
            ),
            "SW2": _logged_command(
                bridge,
                audit,
                "trunk_sw2_state_after_reopen",
                switch_vlan_state_js(
                    "SW2",
                    [
                        "FastEthernet0/1",
                        "FastEthernet0/2",
                        "GigabitEthernet0/1",
                    ],
                ),
            ),
        }
        after_trunks = {
            "SW1": _logged_command(
                bridge,
                audit,
                "trunk_sw1_port_after_reopen",
                trunk_port_state_js("SW1", "GigabitEthernet0/1"),
            ),
            "SW2": _logged_command(
                bridge,
                audit,
                "trunk_sw2_port_after_reopen",
                trunk_port_state_js("SW2", "GigabitEthernet0/1"),
            ),
        }
        _run_ping(
            bridge,
            audit,
            label="trunk_same_vlan_warmup_after_reopen",
            device="PC1",
            destination="192.168.10.11",
            timeout=args.ping_timeout,
        )
        same_after = _run_ping(
            bridge,
            audit,
            label="trunk_same_vlan_after_reopen",
            device="PC1",
            destination="192.168.10.11",
            timeout=args.ping_timeout,
        )
        trunk_passed = (
            bool(same_vlan.get("success"))
            and not bool(cross_vlan.get("success"))
            and bool(same_after.get("success"))
            and all(not item.get("access") for item in trunk_states.values())
            and all(not item.get("access") for item in after_trunks.values())
            and all(item.get("portUp") for item in trunk_states.values())
            and all(item.get("portUp") for item in after_trunks.values())
            and "trunking" in str(sw1_show.get("output", "")).lower()
        )
        report.update(
            {
                "status": "passed" if trunk_passed else "failed",
                "topology": topology,
                "generated_commands": {
                    "SW1": trunk_switch_config_commands(
                        {"FastEthernet0/1": 10}
                    ),
                    "SW2": trunk_switch_config_commands(
                        {
                            "FastEthernet0/1": 10,
                            "FastEthernet0/2": 20,
                        }
                    ),
                },
                "applied": {
                    "SW1": sw1_vlans,
                    "SW2": sw2_vlans,
                    "trunks": {"SW1": sw1_trunk, "SW2": sw2_trunk},
                },
                "state": {
                    "SW1": sw1_state,
                    "SW2": sw2_state,
                    "trunks": trunk_states,
                },
                "same_vlan_ping": same_vlan,
                "cross_vlan_ping": cross_vlan,
                "show_trunk": sw1_show,
                "state_after_reopen": after_states,
                "trunks_after_reopen": after_trunks,
                "same_vlan_ping_after_reopen": same_after,
                "saved_file": saved,
            }
        )
        audit.record("trunk_verification_finished", **report)
        if not trunk_passed:
            raise ScriptBridgeError(f"Trunk verification failed: {report!r}")
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        audit.record("run_failed", status="failed", error=report["error"])
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


def _configure_wireless_dsl(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    network: CompiledNetwork,
    *,
    label: str,
) -> dict[str, object]:
    if network.wireless is None:
        return {}
    wireless = network.wireless
    encrypt_type = 0 if wireless.encryption == "open" else 5
    report: dict[str, object] = {
        "access_point": _logged_command(
            bridge,
            audit,
            f"{label}_ap",
            configure_wireless_ap_js(
                wireless.access_point,
                wireless.ssid,
                encrypt_type=encrypt_type,
                psk=wireless.passphrase,
            ),
        ),
        "clients": [],
    }
    for client in wireless.clients:
        report["clients"].append(
            _logged_command(
                bridge,
                audit,
                f"{label}_client_{client}",
                associate_wireless_client_js(
                    client,
                    wireless.ssid,
                    encrypt_type=encrypt_type,
                    psk=wireless.passphrase,
                ),
            )
        )
    return report


def _run_dsl_output_assertions(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    network: CompiledNetwork,
    *,
    label: str,
    timeout: float,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for index, spec in enumerate(network.output_assertions, start=1):
        invocation = _run_ios_cli(
            bridge,
            audit,
            label=f"{label}_{index:02d}_{spec.name}",
            device=spec.device,
            commands=[spec.command],
            timeout=timeout,
            prepare_boot_dialog=True,
        )
        output = str(invocation.get("output", ""))
        lowered = output.lower()
        missing = [
            expected
            for expected in spec.expected_contains
            if expected.lower() not in lowered
        ]
        results.append(
            {
                "name": spec.name,
                "device": spec.device,
                "command": spec.command,
                "expected_contains": list(spec.expected_contains),
                "missing": missing,
                "passed": not missing,
                "raw_output": output,
            }
        )
    return results


def _configure_dsl_host_with_retry(
    bridge: PTBridgeServer,
    audit: JsonlAuditLogger,
    *,
    label: str,
    device: str,
    port: str,
    ip: str,
    mask: str,
    gateway: str | None,
) -> object:
    last_error: ScriptBridgeError | None = None
    for attempt in range(1, 4):
        try:
            return _logged_command(
                bridge,
                audit,
                f"{label}_attempt_{attempt}",
                configure_host_ip_js(device, port, ip, mask, gateway),
            )
        except ScriptBridgeError as exc:
            last_error = exc
            if "device_not_found" not in str(exc):
                raise
            time.sleep(1.0)
    assert last_error is not None
    raise last_error


def command_job_start(args: argparse.Namespace) -> int:
    options = JobOptions(
        bridge_port=args.bridge_port,
        result_timeout=args.result_timeout,
        connect_timeout=args.connect_timeout,
        cli_timeout=args.cli_timeout,
        ping_timeout=args.ping_timeout,
        traceroute_timeout=args.traceroute_timeout,
        save_timeout=args.save_timeout,
        convergence_rounds=args.convergence_rounds,
        max_runtime=args.max_runtime,
    )
    manager = _job_manager(args, recover=True)
    _json_print(
        manager.start(
            args.path,
            options=options,
            detached=True,
        )
    )
    return 0


def command_job_status(args: argparse.Namespace) -> int:
    job = _job_manager(args).get(args.job_id)
    if job is None:
        _json_print({"found": False, "job_id": args.job_id})
        return 1
    _json_print(job)
    return 0


def command_job_result(args: argparse.Namespace) -> int:
    result = _job_manager(args).result(args.job_id)
    if result is None:
        _json_print({"found": False, "job_id": args.job_id})
        return 1
    _json_print(result)
    return 0


def command_job_cancel(args: argparse.Namespace) -> int:
    job = _job_manager(args).cancel(args.job_id)
    if job is None:
        _json_print({"found": False, "job_id": args.job_id})
        return 1
    _json_print(job)
    return 0


def command_job_list(args: argparse.Namespace) -> int:
    jobs = _job_manager(args).list_jobs()
    _json_print({"count": len(jobs), "jobs": jobs})
    return 0


def command_deploy_dsl(args: argparse.Namespace) -> int:
    try:
        document = load_yaml_document(args.path)
        network = compile_network_dsl(document)
    except (DslCompileError, DslDeploymentError, ValueError) as exc:
        _json_print({"deployed": False, "error": str(exc)})
        return 1

    artifacts = (
        Path(args.artifacts_dir).expanduser().resolve()
        if getattr(args, "artifacts_dir", None)
        else PROJECT_ROOT / "artifacts"
    )
    artifacts.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", network.project).strip("-")
    slug = slug or "network"
    project_path = (artifacts / f"dsl-{slug}.pkt").resolve()
    report_path = (artifacts / f"dsl-{slug}.json").resolve()
    audit_path = (artifacts / f"dsl-{slug}-audit.jsonl").resolve()
    run_id = f"dsl-deploy-{uuid.uuid4().hex[:12]}"
    audit = JsonlAuditLogger(audit_path, run_id)
    bridge = PTBridgeServer(
        port=args.bridge_port,
        result_timeout=args.result_timeout,
    )
    report: dict[str, object] = {
        "run_id": run_id,
        "project": network.project,
        "status": "starting",
        "project_path": str(project_path),
        "audit_path": str(audit_path),
        "plan": network.to_dict(),
    }
    audit.record("dsl_deploy_started", project=network.project)

    try:
        bridge.start()
        bridge.wait_for_extension(timeout=args.connect_timeout)
        resume_from_plan = getattr(args, "resume_from_plan", None)
        if resume_from_plan is None:
            _logged_command(
                bridge,
                audit,
                "dsl_new_project",
                new_project_js(),
            )
            report["topology_devices"] = _logged_command(
                bridge,
                audit,
                "dsl_topology_devices",
                topology_devices_js(network),
            )
            time.sleep(2)
            report["topology_links"] = _logged_command(
                bridge,
                audit,
                "dsl_topology_links",
                topology_links_js(network),
            )
            _logged_command(
                bridge,
                audit,
                "dsl_fast_forward_after_topology",
                fast_forward_js(),
            )
            time.sleep(2)

            host_readbacks: list[object] = []
            for item in network.host_addresses:
                interface = ipaddress.ip_interface(item.address)
                host_readbacks.append(
                    _configure_dsl_host_with_retry(
                        bridge,
                        audit,
                        label=f"dsl_host_{item.device}",
                        device=item.device,
                        port=item.port,
                        ip=str(interface.ip),
                        mask=str(interface.netmask),
                        gateway=item.gateway,
                    )
                )
            report["host_addresses"] = host_readbacks

            ipv6_readbacks: list[object] = []
            for item in network.host_ipv6_addresses:
                ipv6_readbacks.append(
                    _logged_command(
                        bridge,
                        audit,
                        f"dsl_host_ipv6_{item.device}",
                        configure_host_ipv6_js(
                            item.device,
                            item.port,
                            item.address,
                            item.gateway,
                        ),
                    )
                )
            report["host_ipv6_addresses"] = ipv6_readbacks
        else:
            report["resume_from_plan"] = int(resume_from_plan)

        command_results: list[object] = []
        for index, plan in enumerate(network.command_plans, start=1):
            if resume_from_plan is not None and index < int(resume_from_plan):
                continue
            if plan.module == "interface-ipv4":
                interface_target = next(
                    (
                        item
                        for item in network.router_interfaces
                        if item.device == plan.device
                    ),
                    None,
                )
                if interface_target is None:
                    raise ScriptBridgeError(
                        f"No structured interface plan for {plan.device}"
                    )
                structured: dict[str, dict[str, str]] = {}
                virtual: list[tuple[str, str]] = []
                for port, address in interface_target.interfaces:
                    if port.lower().startswith(("loopback", "tunnel")):
                        virtual.append((port, address))
                        continue
                    interface = ipaddress.ip_interface(address)
                    structured[port] = {
                        "ip": str(interface.ip),
                        "mask": str(interface.netmask),
                    }
                if structured:
                    command_results.append(
                        _logged_command(
                            bridge,
                            audit,
                            f"dsl_plan_{index:02d}_interface-ipv4_structured",
                            configure_router_ipv4_js(plan.device, structured),
                            timeout=args.cli_timeout,
                        )
                    )
                if virtual:
                    commands = ["configure terminal"]
                    for port, address in virtual:
                        interface = ipaddress.ip_interface(address)
                        commands.extend(
                            [
                                f"interface {port}",
                                (
                                    f"ip address {interface.ip} "
                                    f"{interface.netmask}"
                                ),
                                "no shutdown",
                                "exit",
                            ]
                        )
                    commands.extend(["end", "write memory"])
                    command_results.append(
                        _run_ios_cli(
                            bridge,
                            audit,
                            label=f"dsl_plan_{index:02d}_interface-virtual",
                            device=plan.device,
                            commands=commands,
                            timeout=args.cli_timeout,
                            prepare_boot_dialog=True,
                        )
                    )
                continue
            command_results.append(
                _run_ios_cli(
                    bridge,
                    audit,
                    label=f"dsl_plan_{index:02d}_{plan.module}",
                    device=plan.device,
                    commands=plan.as_list(),
                    timeout=args.cli_timeout,
                    prepare_boot_dialog=True,
                )
            )
        report["command_plans"] = command_results

        report["wireless"] = _configure_wireless_dsl(
            bridge,
            audit,
            network,
            label="dsl_wireless",
        )

        dhcp_clients: list[object] = []
        for item in network.dhcp_clients:
            dhcp_clients.append(
                _logged_command(
                    bridge,
                    audit,
                    f"dsl_dhcp_client_{item.device}",
                    configure_dhcp_client_js(item.device, item.port),
                )
            )
        report["dhcp_clients"] = dhcp_clients

        for device in network.devices:
            if device.device_type == "router":
                _run_ios_cli(
                    bridge,
                    audit,
                    label=f"dsl_prepare_{device.device_id}",
                    device=device.device_id,
                    commands=[],
                    timeout=args.cli_timeout,
                    prepare_boot_dialog=True,
                )
        _wait_for_protocol_convergence(
            bridge,
            audit,
            "dsl_deploy",
            rounds=args.convergence_rounds,
        )
        advanced_verification = _run_dsl_advanced_verification(
            bridge,
            audit,
            network,
            label="dsl_advanced",
            traceroute_timeout=args.traceroute_timeout,
        )
        report["advanced_verification"] = advanced_verification
        report["output_assertions"] = _run_dsl_output_assertions(
            bridge,
            audit,
            network,
            label="dsl_output_assertions",
            timeout=args.cli_timeout,
        )
        report["dhcp_leases"] = _collect_dsl_dhcp_leases(
            bridge,
            audit,
            network,
        )
        verification = _run_dsl_verification(
            bridge,
            audit,
            network,
            label="dsl_verify",
            ping_timeout=args.ping_timeout,
        )
        report["verification"] = verification
        nat_translations: dict[str, object] = {}
        for plan in network.command_plans:
            if plan.module != "nat-pat":
                continue
            nat_translations[plan.device] = _run_ios_cli(
                bridge,
                audit,
                label=f"dsl_nat_translations_{plan.device}",
                device=plan.device,
                commands=["show ip nat translations"],
                timeout=args.cli_timeout,
            )
        report["nat_translations"] = nat_translations

        failure_actions: list[object] = []
        for item in network.link_failures:
            failure_actions.append(
                _logged_command(
                    bridge,
                    audit,
                    f"dsl_link_failure_{item.name}",
                    set_port_power_js(item.device, item.port, False),
                )
            )
        report["link_failures"] = failure_actions
        if network.link_failures:
            _wait_for_protocol_convergence(
                bridge,
                audit,
                "dsl_failure_convergence",
                rounds=args.convergence_rounds,
            )
            failure_specs = (
                network.failure_verification
                if network.failure_verification
                else network.verification
            )
            report["verification_after_failure"] = _run_dsl_verification(
                bridge,
                audit,
                network,
                label="dsl_verify_after_failure",
                ping_timeout=args.ping_timeout,
                specs=failure_specs,
            )
            failure_routes = (
                network.failure_route_assertions
                if network.failure_route_assertions
                else network.route_assertions
            )
            failure_traces = (
                network.failure_traceroutes
                if network.failure_traceroutes
                else network.traceroutes
            )
            report["advanced_verification_after_failure"] = (
                _run_dsl_advanced_verification(
                    bridge,
                    audit,
                    network,
                    label="dsl_advanced_after_failure",
                    traceroute_timeout=args.traceroute_timeout,
                    route_assertions=failure_routes,
                    traceroutes=failure_traces,
                )
            )

        saved = _save_and_wait(
            bridge,
            audit,
            project_path,
            args.save_timeout,
        )
        report["saved_file"] = saved
        _logged_command(
            bridge,
            audit,
            "dsl_new_for_reopen",
            new_project_js(),
        )
        _logged_command(
            bridge,
            audit,
            "dsl_reopen",
            open_project_js(project_path),
        )
        report["wireless_after_reopen"] = _configure_wireless_dsl(
            bridge,
            audit,
            network,
            label="dsl_wireless_after_reopen",
        )
        for device in network.devices:
            if device.device_type == "router":
                _run_ios_cli(
                    bridge,
                    audit,
                    label=f"dsl_reopen_prepare_{device.device_id}",
                    device=device.device_id,
                    commands=[],
                    timeout=args.cli_timeout,
                    prepare_boot_dialog=True,
                )
        _wait_for_protocol_convergence(
            bridge,
            audit,
            "dsl_reopen",
            rounds=args.convergence_rounds,
        )
        report["topology_after_reopen"] = _logged_command(
            bridge,
            audit,
            "dsl_topology_after_reopen",
            topology_state_js(),
        )
        reopened_hosts: list[object] = []
        for item in network.host_addresses:
            reopened_hosts.append(
                _logged_command(
                    bridge,
                    audit,
                    f"dsl_reopen_host_{item.device}",
                    host_ip_state_js(item.device, item.port),
                )
            )
        report["host_addresses_after_reopen"] = reopened_hosts
        reopened_ipv6_hosts: list[object] = []
        for item in network.host_ipv6_addresses:
            reopened_ipv6_hosts.append(
                _logged_command(
                    bridge,
                    audit,
                    f"dsl_reopen_host_ipv6_{item.device}",
                    host_ipv6_state_js(item.device, item.port),
                )
            )
        report["host_ipv6_addresses_after_reopen"] = reopened_ipv6_hosts
        reopened_dhcp_clients: list[object] = []
        for item in network.dhcp_clients:
            reopened_dhcp_clients.append(
                _logged_command(
                    bridge,
                    audit,
                    f"dsl_reopen_dhcp_client_{item.device}",
                    host_ip_state_js(item.device, item.port),
                )
            )
        report["dhcp_clients_after_reopen"] = reopened_dhcp_clients
        reopen_specs = (
            network.failure_verification
            if network.link_failures and network.failure_verification
            else network.verification
        )
        reopen_routes = (
            network.failure_route_assertions
            if network.link_failures and network.failure_route_assertions
            else network.route_assertions
        )
        reopen_traces = (
            network.failure_traceroutes
            if network.link_failures and network.failure_traceroutes
            else network.traceroutes
        )
        advanced_after = _run_dsl_advanced_verification(
            bridge,
            audit,
            network,
            label="dsl_advanced_after_reopen",
            traceroute_timeout=args.traceroute_timeout,
            route_assertions=reopen_routes,
            traceroutes=reopen_traces,
        )
        report["advanced_verification_after_reopen"] = advanced_after
        report["output_assertions_after_reopen"] = _run_dsl_output_assertions(
            bridge,
            audit,
            network,
            label="dsl_output_assertions_after_reopen",
            timeout=args.cli_timeout,
        )
        verification_after = _run_dsl_verification(
            bridge,
            audit,
            network,
            label="dsl_verify_after_reopen",
            ping_timeout=args.ping_timeout,
            specs=reopen_specs,
        )
        report["verification_after_reopen"] = verification_after

        advanced_passed = all(
            item.get("passed")
            for group in (advanced_verification, advanced_after)
            for key in ("route_assertions", "traceroutes")
            for item in group.get(key, [])
        )
        failure_advanced = report.get(
            "advanced_verification_after_failure",
            {"route_assertions": [], "traceroutes": []},
        )
        passed = (
            all(item.get("passed") for item in verification)
            and all(item.get("passed") for item in verification_after)
            and advanced_passed
            and all(
                item.get("passed")
                for group in (
                    report.get("output_assertions", []),
                    report.get("output_assertions_after_reopen", []),
                )
                for item in group
            )
            and all(
                item.get("passed")
                for item in report.get("verification_after_failure", [])
            )
            and _dhcp_leases_are_valid(
                report.get("dhcp_clients_after_reopen", []),
                network.dhcp_networks,
            )
            and all(
                item.get("passed")
                for key in ("route_assertions", "traceroutes")
                for item in failure_advanced.get(key, [])
            )
        )
        report["status"] = "passed" if passed else "failed"
        audit.record("dsl_deploy_finished", status=report["status"])
        if not passed:
            raise ScriptBridgeError(
                "DSL verification failed before or after reopen"
            )
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        audit.record("dsl_deploy_failed", error=report["error"])
        raise
    finally:
        bridge.stop()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    _json_print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Packet Tracer backend bootstrap for the LLM PT project"
    )
    parser.add_argument(
        "--pt-root",
        help="Packet Tracer installation directory; defaults to BONUS_PT_ROOT",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate local paths and config")
    doctor.set_defaults(func=command_doctor)

    validate_dsl = subparsers.add_parser(
        "validate-dsl",
        help="Validate a YAML network DSL file against schema and semantics",
    )
    validate_dsl.add_argument("path")
    validate_dsl.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="JSON Schema file path",
    )
    validate_dsl.set_defaults(func=command_validate_dsl)

    check_commands = subparsers.add_parser(
        "check-commands",
        help="Validate IOS commands against the allowlist and destructive blacklist",
    )
    check_commands.add_argument(
        "commands",
        nargs="+",
        help="Quoted command strings to validate; nothing is executed",
    )
    check_commands.set_defaults(func=command_check_commands)

    compile_dsl = subparsers.add_parser(
        "compile-dsl",
        help="Compile YAML DSL into topology, configuration, and verification plans",
    )
    compile_dsl.add_argument("path")
    compile_dsl.add_argument("--output")
    compile_dsl.set_defaults(func=command_compile_dsl)

    deploy_dsl = subparsers.add_parser(
        "deploy-dsl",
        help="Validate, compile, deploy, save, reopen, and verify a YAML network",
    )
    deploy_dsl.add_argument("path")
    deploy_dsl.add_argument("--artifacts-dir")
    deploy_dsl.add_argument("--bridge-port", type=int, default=54321)
    deploy_dsl.add_argument("--result-timeout", type=float, default=30.0)
    deploy_dsl.add_argument("--connect-timeout", type=float, default=90.0)
    deploy_dsl.add_argument("--cli-timeout", type=float, default=45.0)
    deploy_dsl.add_argument("--ping-timeout", type=float, default=25.0)
    deploy_dsl.add_argument("--traceroute-timeout", type=float, default=40.0)
    deploy_dsl.add_argument("--save-timeout", type=float, default=20.0)
    deploy_dsl.add_argument("--convergence-rounds", type=int, default=3)
    deploy_dsl.add_argument(
        "--resume-from-plan",
        type=int,
        help="Reuse the current topology and replay command plans from this index",
    )
    deploy_dsl.set_defaults(func=command_deploy_dsl)

    job = subparsers.add_parser(
        "job",
        help="Start and inspect persistent long-running deployment jobs",
    )
    job_actions = job.add_subparsers(dest="job_action", required=True)

    job_start = job_actions.add_parser("start", help="Start a deployment job")
    job_start.add_argument("path")
    job_start.add_argument("--data-dir")
    job_start.add_argument("--bridge-port", type=int, default=54321)
    job_start.add_argument("--result-timeout", type=float, default=180.0)
    job_start.add_argument("--connect-timeout", type=float, default=60.0)
    job_start.add_argument("--cli-timeout", type=float, default=120.0)
    job_start.add_argument("--ping-timeout", type=float, default=30.0)
    job_start.add_argument("--traceroute-timeout", type=float, default=45.0)
    job_start.add_argument("--save-timeout", type=float, default=60.0)
    job_start.add_argument("--convergence-rounds", type=int, default=3)
    job_start.add_argument("--max-runtime", type=float, default=1800.0)
    job_start.set_defaults(func=command_job_start)

    for action, help_text, function in (
        ("status", "Return the current state of a deployment job", command_job_status),
        ("result", "Return the persisted result of a deployment job", command_job_result),
        ("cancel", "Cancel a queued or running deployment job", command_job_cancel),
    ):
        command = job_actions.add_parser(action, help=help_text)
        command.add_argument("job_id")
        command.add_argument("--data-dir")
        command.set_defaults(func=function)

    job_list = job_actions.add_parser("list", help="List deployment jobs")
    job_list.add_argument("--data-dir")
    job_list.set_defaults(func=command_job_list)

    launch = subparsers.add_parser(
        "launch-gui", help="Launch Packet Tracer with the Script Module workflow"
    )
    launch.set_defaults(func=command_launch_gui)

    bridge = subparsers.add_parser(
        "script-bridge", help="Run the local bridge for the PT Script Module"
    )
    bridge.add_argument("--bridge-port", type=int, default=54321)
    bridge.add_argument("--result-timeout", type=float, default=30.0)
    bridge.set_defaults(func=command_script_bridge)

    script_demo = subparsers.add_parser(
        "script-demo",
        help="Run the Script Engine create/save/reopen smoke test",
    )
    script_demo.add_argument("--bridge-port", type=int, default=54321)
    script_demo.add_argument("--result-timeout", type=float, default=30.0)
    script_demo.add_argument("--connect-timeout", type=float, default=90.0)
    script_demo.add_argument("--save-timeout", type=float, default=20.0)
    script_demo.set_defaults(func=command_script_demo)

    config_ping = subparsers.add_parser(
        "config-ping-demo",
        help="Configure host IPs, run ping verification, and write an audit log",
    )
    config_ping.add_argument("--bridge-port", type=int, default=54321)
    config_ping.add_argument("--result-timeout", type=float, default=30.0)
    config_ping.add_argument("--connect-timeout", type=float, default=90.0)
    config_ping.add_argument("--ping-timeout", type=float, default=15.0)
    config_ping.add_argument("--save-timeout", type=float, default=20.0)
    config_ping.set_defaults(func=command_config_ping_demo)

    repair_demo = subparsers.add_parser(
        "repair-demo",
        help="Inject a host mask fault, diagnose it, repair it, and verify",
    )
    repair_demo.add_argument("--bridge-port", type=int, default=54321)
    repair_demo.add_argument("--result-timeout", type=float, default=30.0)
    repair_demo.add_argument("--connect-timeout", type=float, default=90.0)
    repair_demo.add_argument("--ping-timeout", type=float, default=20.0)
    repair_demo.add_argument("--save-timeout", type=float, default=20.0)
    repair_demo.set_defaults(func=command_repair_demo)

    config_suite = subparsers.add_parser(
        "config-suite-demo",
        help="Test VLAN isolation and router ACL configuration end to end",
    )
    config_suite.add_argument("--bridge-port", type=int, default=54321)
    config_suite.add_argument("--result-timeout", type=float, default=30.0)
    config_suite.add_argument("--connect-timeout", type=float, default=90.0)
    config_suite.add_argument("--cli-timeout", type=float, default=45.0)
    config_suite.add_argument("--ping-timeout", type=float, default=20.0)
    config_suite.add_argument("--save-timeout", type=float, default=20.0)
    config_suite.set_defaults(func=command_config_suite_demo)

    routing_suite = subparsers.add_parser(
        "routing-suite-demo",
        help="Test static/default, RIP v1/v2, and OSPF configuration",
    )
    routing_suite.add_argument("--bridge-port", type=int, default=54321)
    routing_suite.add_argument("--result-timeout", type=float, default=30.0)
    routing_suite.add_argument("--connect-timeout", type=float, default=90.0)
    routing_suite.add_argument("--cli-timeout", type=float, default=45.0)
    routing_suite.add_argument("--ping-timeout", type=float, default=20.0)
    routing_suite.add_argument("--save-timeout", type=float, default=20.0)
    routing_suite.set_defaults(func=command_routing_suite_demo)

    trunk_suite = subparsers.add_parser(
        "trunk-suite-demo",
        help="Test VLAN access ports and an inter-switch trunk",
    )
    trunk_suite.add_argument("--bridge-port", type=int, default=54321)
    trunk_suite.add_argument("--result-timeout", type=float, default=30.0)
    trunk_suite.add_argument("--connect-timeout", type=float, default=90.0)
    trunk_suite.add_argument("--cli-timeout", type=float, default=45.0)
    trunk_suite.add_argument("--ping-timeout", type=float, default=20.0)
    trunk_suite.add_argument("--save-timeout", type=float, default=20.0)
    trunk_suite.set_defaults(func=command_trunk_suite_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        ScriptBridgeError,
        OSError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

