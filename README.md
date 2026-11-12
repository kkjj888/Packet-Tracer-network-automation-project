# Bonus: Packet Tracer Backend Bootstrap

This directory contains the first backend milestone for the LLM-driven Packet Tracer project.

The current goal is deliberately narrow:

```text
install a PT Script Module
-> start a local Python HTTP bridge
-> send controlled JavaScript to PT's Script Engine
-> create a new PKT
-> add devices and links
-> save the PKT
-> reopen it and read back device/link counts
```

The current backend includes a YAML network DSL, JSON Schema validation,
network-semantic checks, command-safety checks, and verified Packet Tracer
configuration/acceptance loops. Agent and frontend integration remain later
milestones.

See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for the current architecture,
completed capabilities, test matrix, remaining work, and next milestones.

## Current Result

Validate a network DSL document:

```powershell
python -m pt_agent validate-dsl examples\campus-vlan.yaml
python -m pt_agent validate-dsl examples\ospf-routing.yaml
python -m pt_agent compile-dsl examples\campus-vlan.yaml
python -m pt_agent deploy-dsl examples\campus-vlan.yaml
python -m pt_agent deploy-dsl examples\ospf-routing.yaml
```

See [`docs/DSL_VALIDATION.md`](docs/DSL_VALIDATION.md) for the DSL structure,
validation layers, deployment flow, and safety behavior.

The Script Engine route has been verified end to end against Packet Tracer
9.0.1:

- Extension connected to the Python bridge at `127.0.0.1:54321`.
- Created `PC1`, `PC2`, and `SW1`.
- Created both switch links through `LogicalWorkspace.createLink()`.
- Saved a 48,080-byte PKT file.
- Reopened the PKT and read back the same three devices and two links.

Evidence:

```text
artifacts/script-engine-smoke.pkt
artifacts/script-engine-smoke.json
```

The first configuration/verification loop is also verified:

```text
PC1: 192.168.1.10/24
PC2: 192.168.1.11/24
Ping: 4 sent, 4 received, 0 lost
Save and reopen: addresses preserved
Audit: 52 independent JSONL events
```

Evidence:

```text
artifacts/config-ping-smoke.pkt
artifacts/config-ping-smoke.json
artifacts/config-ping-audit.jsonl
```

The first deterministic fault-repair loop is also verified:

```text
Baseline Ping: 4/4 successful
Injected fault: PC1 mask 255.255.255.252 instead of 255.255.255.0
Faulted Ping: 0 successful replies
Diagnosis: HOST_MASK_MISMATCH on PC1:FastEthernet0
Repair: reapply the expected mask on PC1 only
Final Ping: 4/4 successful
Repair rounds: 1
```

Evidence:

```text
artifacts/repair-smoke.pkt
artifacts/repair-smoke.json
artifacts/repair-audit.jsonl
```

Packet Tracer automatically adds one internal `Power Distribution Device0`
to a new canvas, so the raw device count is four while the intended topology
contains three devices.

## Script Engine Route

The main route is:

```text
Python backend
  -> local HTTP bridge (127.0.0.1:54321)
  -> Packet Tracer Script Module (`.pts`)
  -> PT Script Engine
  -> PT native `ipc.*` JavaScript API
```

The Python side builds each JavaScript expression, queues it for PT, receives
the PT result, and performs the acceptance checks. The Script Module only
polls the bridge and executes code inside Packet Tracer.

### Install The Script Module

The validation build uses the MIT-licensed extension from
`Jcorderop02/packet-tracer-mcp`, vendored at:

```text
vendor/mcp-bridge.pts
```

In Packet Tracer:

```text
Extensions
-> Scripting
-> Configure PT Script Modules
-> Add
-> select vendor/mcp-bridge.pts
-> Launch
```

The module remains registered after a normal Packet Tracer restart.

### Run The Script Engine Smoke Test

Run:

```powershell
python -m pt_agent script-demo
```

While the command is waiting for the extension, open:

```text
Extensions -> MCP Bridge
```

The command starts the bridge, waits for the module, then performs:

```text
fileNew(false)
-> add PC1, PC2, and SW1
-> create two Ethernet links
-> save .pkt
-> fileNew(false)
-> fileOpen(saved .pkt)
-> read device names/models and link count
```

To run the bridge separately:

```powershell
python -m pt_agent script-bridge
```

The extension polls `http://127.0.0.1:54321/next`.

To run the static-IP and Ping verification loop:

```powershell
python -m pt_agent config-ping-demo
```

This creates the topology, configures both PCs, performs a warm-up Ping,
executes the measured 4-packet Ping, saves the project, reopens it, and checks
that both addresses survived the round trip.

To run the deterministic fault-injection and repair loop:

```powershell
python -m pt_agent repair-demo
```

This proves a working baseline, injects a wrong host mask, verifies that Ping
fails, compares PT's live address state with the expected configuration,
applies the minimum repair, and verifies connectivity again.

### Script Engine Scope Implemented Here

- Local HTTP command bridge
- Script Module connection detection
- Python-to-JavaScript command transport
- Hex result decoding
- New project
- Add router/switch/PC-compatible devices through native `ipc.*`
- Rename and power devices
- Create links with explicit endpoints
- Read device names/models and link count
- Configure and read back static host addresses
- Configure and read back VLANs and access-port assignments
- Configure `SwitchPortMode` trunks and read back live trunk state
- Configure and read back router IPv4 interfaces
- Configure numbered ACLs and interface bindings
- Add static/default routes and read PT's structured routing table
- Configure RIP v1/v2 through PT's native CLI and verify convergence
- Configure OSPF process IDs, wildcard masks, and areas
- Run Ping through the PT host command line
- Parse complete Ping statistics and reject partial false positives
- Deterministic host address diagnosis
- Minimum repair for host IP or mask mismatch
- Re-test after repair and save the repaired PKT
- Write append-only JSONL audit events
- Save to PKT
- Open an existing PKT
- File existence and size checks

### Current Limitation

The vendored validation `.pts` supports the HTTP command channel. The
file-mailbox fallback described by the Mats2208 project is not part of this
vendor package.

The final project should replace this temporary module with our own Script
Module that supports:

- request IDs and correlated results;
- a local authentication token;
- an allowlisted command protocol;
- HTTP polling while its window is open;
- a file mailbox when the extension window is closed.

## Legacy ExApp / PTMP Experiment

The deprecated PTMP/ExApp code and build artifacts are archived under
[`trash/ptmp_exapp`](trash/ptmp_exapp/README.md). The active CLI no longer
imports that code.

## Requirements

- Windows
- Python 3.11 or newer
- Cisco Packet Tracer 9.0.1

The default Packet Tracer root is:

```text
D:\Cisco Packet Tracer 9.0.1
```

Override it with `--pt-root` or the `BONUS_PT_ROOT` environment variable.

### First Run

From `D:\codex\bonus`:

```powershell
python -m pt_agent doctor
python -m pt_agent launch-gui
```

The first command validates the local PT installation. Then open:

```text
Extensions -> Scripting -> Configure PT Script Modules
```

Register `vendor/mcp-bridge.pts`, launch `MCP Bridge`, and open its extension
window. The extension polls `http://127.0.0.1:54321` while it is running.

Router and switch integration tests also dismiss PT's first-boot
configuration dialog. That dialog is a real forwarding blocker: structured
IPC calls can write interface configuration while the dialog is open, but
packets are not forwarded until the dialog is answered `no`.

## Useful Commands

```powershell
python -m pt_agent --help
python -m pt_agent doctor
python -m pt_agent script-demo
python -m pt_agent script-bridge
python -m pt_agent launch-gui
python -m pt_agent config-ping-demo
python -m pt_agent repair-demo
python -m pt_agent config-suite-demo
python -m pt_agent routing-suite-demo
python -m pt_agent trunk-suite-demo
```

## Verified Configuration Matrix

The current integration suites run against Packet Tracer 9.0.1 and save both
PKT projects and JSONL audit traces under `artifacts/`.

| Area | Verified behavior | Primary artifact |
|---|---|---|
| Host addressing and Ping | Warm-up, 4-packet statistics, save/reopen | `config-ping-smoke.json` |
| Fault repair | Inject wrong mask, diagnose, minimum repair, verify | `repair-smoke.json` |
| VLAN access ports | VLAN 10/20 persistence; same-VLAN Ping 4/4 | `config-suite-smoke.json` |
| ACL | Routed baseline 4/4; deny rule changes result to 0/4 | `config-suite-smoke.json` |
| Static/default routing | Default and return route persist across reopen | `config-routing-suite.json` |
| RIPv1/v2 | RIPv1 failed with auto-summary; RIPv2 plus `no auto-summary` passed | `config-routing-suite.json` |
| OSPF | Process 100, wildcard masks, area 0, OSPF route and Ping persisted | `config-routing-suite.json` |
| Trunk | Same VLAN traverses trunk 4/4; cross VLAN is isolated | `config-trunk-suite.json` |

The routing suite verifies PT's live routing table, not only command output.
For OSPF, R1 learns `172.16.20.0/24` via `10.0.0.2` with administrative
distance 110. For RIPv2, the remote route is learned with administrative
distance 120.

## Current Boundaries

The following are not yet part of this verification matrix:

- NAT/PAT and DHCP pools
- IPv6 and tunnels
- BGP and redundant-path failover
- Traceroute and structured PDU assertions
- YAML DSL and JSON Schema validation
- Production authentication and request correlation in our own `.pts`

The audited tests are local Packet Tracer simulations only.

## Design Notes

- PKT contains the actual network project.
- Python owns orchestration, validation, assertions, reporting, and audit.
- JavaScript only executes Packet Tracer's native IPC operations.
- Interface state and reachability are read back from PT before a step passes.
- PT's first-boot dialog must be dismissed before packet forwarding works.
- The vendored bridge is for local validation; production needs a token,
  request IDs, an allowlist, and a file-mailbox fallback.
- This milestone is local-simulation only.

