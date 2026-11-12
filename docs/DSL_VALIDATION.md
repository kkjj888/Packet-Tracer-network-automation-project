# YAML DSL and Validation

The network DSL is a constrained YAML document describing intent rather than
raw Packet Tracer JavaScript or IOS commands.

## Validation Layers

1. **YAML parsing** rejects invalid syntax and non-mapping roots.
2. **JSON Schema** checks required fields, types, enums, ranges, and patterns.
3. **Network semantics** checks references and network logic.
4. **Command safety** checks generated commands against allow and deny rules.

The implementation is in `pt_agent/validation.py`; the schema is
`schema/network.schema.json`.

## Schema Versus Semantics

Schema validation catches structural errors such as:

- an unsupported device type;
- a VLAN ID that is not an integer in the range 1-4094;
- an ACL action other than `permit` or `deny`;
- a missing required field.

Semantic validation catches:

- duplicate device IDs or IPv4 addresses;
- network and broadcast addresses assigned to interfaces;
- gateways outside their interface subnet;
- unknown device, VLAN, or ACL references;
- ports connected more than once;
- unreachable static-route next hops;
- OSPF networks with host bits or no connected interface;
- non-contiguous ACL wildcard masks;
- connectivity tests referencing unknown devices.

Validation results are structured and point to a path such as
`$.devices[0].type` or `routing.ospf.networks[2].network`.

## Command Safety

`CommandSafetyValidator` fails closed. It blocks:

- `reload`
- `write erase`
- `erase startup-config`
- `format`
- `delete`
- `confreg`
- `debug all`
- `no ip routing`
- multiline commands and shell-like injection patterns
- commands outside the supported IOS allowlist

The allowlist is intentionally narrow. Adding a new feature requires a new
template and tests; the system does not execute arbitrary LLM command output.

## Examples

- `examples/campus-vlan.yaml`: VLAN access ports, inter-switch trunk, and
  expected connectivity.
- `examples/ospf-routing.yaml`: routed IPv4 interfaces and OSPF area 0.

Run:

```powershell
python -m pt_agent validate-dsl examples\campus-vlan.yaml
python -m pt_agent validate-dsl examples\ospf-routing.yaml
python -m pt_agent compile-dsl examples\campus-vlan.yaml
python -m pt_agent deploy-dsl examples\campus-vlan.yaml
python -m pt_agent deploy-dsl examples\ospf-routing.yaml
```

## Deployment Flow

`deploy-dsl` performs the complete local Packet Tracer flow:

1. YAML and JSON Schema validation.
2. Network-semantic and command-safety validation.
3. Deterministic compilation into topology, host, command, and verification
   plans.
4. Project creation and topology deployment.
5. Host IPv4 and IOS command-plan deployment.
6. Protocol convergence.
7. Positive and negative connectivity verification.
8. PKT save and reopen.
9. Host address, topology, and connectivity verification after reopen.
10. JSON report and JSONL audit output under `artifacts/`.

The campus example verifies VLAN/Trunk isolation. The OSPF example verifies
cross-subnet routing through YAML-generated interface and OSPF commands.

## Dependency Setup

```powershell
python -m pip install -r requirements.txt
```
