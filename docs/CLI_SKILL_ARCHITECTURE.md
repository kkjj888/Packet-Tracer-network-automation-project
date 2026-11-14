# CLI + Skill Architecture

## Product Boundary

The current product is a Windows CLI with a companion Codex skill. It does not
embed an agent and does not expose an MCP server.

```text
Agent
  -> Shell
  -> pt-agent CLI
  -> Application Services
  -> Windows Packet Tracer Runtime
  -> PT Bridge
  -> Packet Tracer
```

The agent supplies reasoning and user interaction. The CLI supplies deterministic
validation, compilation, deployment, persistence, and evidence collection. The
skill defines the operating sequence and evidence requirements.

## Layers

```text
pt_agent/
├── application/          Stable validation and compilation services
├── jobs/                 Persistent long-running deployment jobs
├── runtime/              Windows PT discovery and process integration
├── compiler/             IOS command templates
├── dsl_compiler.py       Full YAML-to-plan compilation
├── validation.py         Schema, semantic, and command-safety checks
├── script_backend.py     PT Script Engine JavaScript builders
├── script_bridge.py      Local HTTP bridge
├── dsl_deployment.py     Verification evaluation
└── cli.py                Command adapter and deployment orchestration
```

New transports must call application services or the public CLI. They must not
import private JavaScript builders or bypass command validation.

## Agent-Facing Commands

Read-only commands return JSON:

```powershell
pt-agent doctor
pt-agent validate-dsl <file>
pt-agent compile-dsl <file>
pt-agent job status <job-id>
pt-agent job result <job-id>
pt-agent job list
```

Mutation commands:

```powershell
pt-agent job start <file> --data-dir artifacts\jobs
pt-agent job cancel <job-id> --data-dir artifacts\jobs
```

`deploy-dsl` remains available for direct diagnostics and test automation, but
normal agent use should start a Job so that the operation can be queried and
cancelled independently.

## Job Lifecycle

```text
queued
  -> running / starting
  -> running / deploying
  -> passed / completed
     or failed / completed
     or cancelled
     or timed_out
```

Each job owns one directory:

```text
artifacts/jobs/job-YYYYMMDD-HHMMSS-xxxxxxxx/
├── request.json
├── job.json
├── stdout.log
├── stderr.log
├── worker.stdout.log
├── worker.stderr.log
├── dsl-<project>.pkt
├── dsl-<project>.json
└── dsl-<project>-audit.jsonl
```

The detached worker runs one deployment subprocess. Job state is persisted
atomically after state changes, so a later CLI invocation can query the result.

## Windows Runtime

The runtime is intentionally Windows-only. It resolves the Packet Tracer
installation in this order:

```text
PT_AGENT_PT_ROOT
-> known local paths
-> Program Files Cisco Packet Tracer directories
```

The runtime checks `bin/PacketTracer.exe` and `vendor/mcp-bridge.pts`. It does
not claim Linux or macOS PT support.

## Security Rules

- YAML and artifact inputs are constrained to the workspace.
- Model-facing workflows use the YAML compiler and CommandPlan allowlist.
- Raw JavaScript and arbitrary IOS command execution are not public tools.
- A job is the unit of cancellation, audit, and artifact ownership.
- Test expectations must not be weakened just to obtain a passing report.

## Skill

The operational skill is:

```text
skills/pt-network-automation/SKILL.md
```

It defines the doctor -> validate -> compile -> job start -> job status ->
job result workflow and routes failure diagnosis to the troubleshooting
playbook.

## Future Optional MCP Adapter

If a later product requires MCP clients, add a transport adapter over the same
application services. The existing compiler, validation, runtime, and Job
storage do not need to move.
