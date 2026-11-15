---
name: pt-network-automation
description: Build, deploy, inspect, and verify Packet Tracer network scenarios through the deterministic pt-agent CLI on Windows. Use for Packet Tracer topology/configuration automation, not for generic network-device work or raw JavaScript execution.
---

# Packet Tracer Network Automation

Use the project CLI as the only mutation interface. Do not import internal
modules with ad-hoc Python, send raw PT JavaScript, or bypass the YAML
compiler and command-safety layer.

## Resolve the executable

Prefer:

```text
pt-agent
```

If the console script is not on `PATH`, use:

```text
python -m pt_agent
```

Run commands from the project workspace so relative YAML and artifact paths
resolve consistently. The current runtime supports Packet Tracer on Windows
only.

## Environment prerequisites

- Windows 10/11, Python 3.11+, Packet Tracer 9.0.1.
- Python dependencies are `PyYAML` and `jsonschema`. If `pip install -e .` is
  not available, run from the project root with the project itself and its
  dependency directory on `PYTHONPATH`.
- Packet Tracer is auto-discovered from the usual install paths. If it is
  installed elsewhere, pass `--pt-root <dir>` or set `PT_AGENT_PT_ROOT`.
- The PT-side contract is `vendor/mcp-bridge.pts`. Load it once per PT session:
  `Extensions -> Scripting -> Configure PT Script Modules -> Add ->
  vendor/mcp-bridge.pts -> Active/Launch`, then open its window.
- Keep the module and the CLI paired: the module must implement the
  `__mcpEval` + hex `/result` protocol used by `pt_agent`. Do **not** load the
  V5.2 `MCP Control Center` module (token + `rid` + `reportResult`) with this
  CLI. It still polls `/next`, so `doctor` may report
  `bridge_connected: true`, but deployment fails with
  `Script Engine returned no result`.
- The bridge is `127.0.0.1:54321`. `deploy-dsl` starts it automatically; do
  not run a second bridge at the same time.
- The module must be launched again after each PT restart unless it is
  configured to start with PT.

## Bridge preflight

`bridge_connected: true` only means some client polled `/next` within the
last 5 seconds. It does not prove the client understands `__mcpEval`.

Before the first real deployment, run the smallest case as a smoke test:

```text
pt-agent deploy-dsl examples/assignment/uc06-home-office-switch.yaml
```

Proceed only if it returns `status: passed` and the report and `.pkt` exist.

## Standard workflow

1. Check the local runtime:

```text
pt-agent doctor --wait-bridge 5
```

Stop if `validation_errors` is non-empty or `bridge_connected` is false.
Packet Tracer must be open with the project's `vendor/mcp-bridge.pts` Script
Module active before deployment. Then run the Bridge preflight smoke test
before the first real deployment.

2. Read the target YAML and validate it:

```text
pt-agent validate-dsl <dsl-path>
```

Do not edit the DSL to make an unexpected failure disappear. Correct the
requested network based on the validation issues.

3. Compile when configuration scope or command plans need review:

```text
pt-agent compile-dsl <dsl-path>
```

4. Deploy directly and wait for the command to finish:

```text
pt-agent deploy-dsl <dsl-path>
```

Allow the shell command enough time for topology creation, configuration,
verification, save, and reopen. Do not terminate a still-running deployment
merely because it takes several minutes.

Success requires all of:

- `status` is `passed`;
- the report `status` is `passed`;
- `report_path`, `project_path`, and `audit_path` exist;
- all requested verification checks passed;
- save, reopen, and post-reopen verification passed.

## Bridge troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `doctor` reports `bridge_connected: false` | PT is closed, the module is not launched, or port 54321 is not listening | Open PT, add/launch `vendor/mcp-bridge.pts`, open its window, rerun `doctor`. |
| `doctor` is connected but `deploy-dsl` ends with `Script Engine returned no result within 30s` | The module speaks a different protocol/version (for example V5.2 token/rid) | Stop. Load the paired `vendor/mcp-bridge.pts`, or use the project's compatibility shim; do not retry blindly or change YAML/expected values. |
| The module shows `Bridge unreachable at :54321` | The Python bridge is not running (normal when no deployment is active) | Start a deployment; `deploy-dsl` starts the bridge itself. |
| `pt-agent: command not found` | The console script is not installed or not on `PATH` | Use `python -m pt_agent` from the project root. |

A timeout at the bridge layer is not a network-under-test failure. Fix the
transport before touching the YAML or its expected values.

## Failure handling

Evidence order:

```text
deploy command output and exit code
-> report.json
-> audit.jsonl
-> live PT state only when needed
```

For network failures, read `docs/LLM_TROUBLESHOOTING_PLAYBOOK.md` from the
project workspace containing `pt_agent/`.
For DSL fields and validation rules, read `docs/DSL_VALIDATION.md`.
Before proposing or validating destructive commands, read
`docs/COMMAND_SAFETY.md`.

Never:

- modify expected Ping, route, or Traceroute values solely to obtain `passed`;
- remove ACL/NAT/routing configuration without evidence identifying that scope;
- use device reload, startup-config erase, `debug all`, or unrestricted IOS;
- claim a PT feature works when the report records a platform limitation;
- treat `up/up` as proof that a tunnel or end-to-end path works.

If implementation and test expectation disagree, identify which one is wrong
from topology, route tables, protocol state, and live output before changing
code or the YAML.
