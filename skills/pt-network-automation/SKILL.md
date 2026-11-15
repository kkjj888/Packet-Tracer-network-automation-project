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

## Standard workflow

1. Check the local runtime:

```text
pt-agent doctor --wait-bridge 5
```

Stop if `validation_errors` is non-empty or `bridge_connected` is false.
Packet Tracer must be open with the project's `vendor/mcp-bridge.pts` Script
Module active before deployment.

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

## Failure handling

Evidence order:

```text
deploy command output and exit code
-> report.json
-> audit.jsonl
-> live PT state only when needed
```

For network failures, read
[`../../docs/LLM_TROUBLESHOOTING_PLAYBOOK.md`](../../docs/LLM_TROUBLESHOOTING_PLAYBOOK.md).
For DSL fields and validation rules, read
[`../../docs/DSL_VALIDATION.md`](../../docs/DSL_VALIDATION.md).
Before proposing or validating destructive commands, read
[`../../docs/COMMAND_SAFETY.md`](../../docs/COMMAND_SAFETY.md).

Never:

- modify expected Ping, route, or Traceroute values solely to obtain `passed`;
- remove ACL/NAT/routing configuration without evidence identifying that scope;
- use device reload, startup-config erase, `debug all`, or unrestricted IOS;
- claim a PT feature works when the report records a platform limitation;
- treat `up/up` as proof that a tunnel or end-to-end path works.

If implementation and test expectation disagree, identify which one is wrong
from topology, route tables, protocol state, and live output before changing
code or the YAML.
