# CLI + Skill Architecture

## Product Boundary

The current product is a Windows CLI with a companion Codex skill. It does not
embed an agent, expose an MCP server, or run background job workers.

```text
Agent
  -> Shell
  -> pt-agent CLI
  -> Windows Packet Tracer Runtime
  -> PT Bridge
  -> Packet Tracer
```

The agent supplies reasoning and user interaction. The CLI supplies
deterministic validation, compilation, deployment, persistence, and evidence
collection. The skill defines the operating sequence and evidence requirements.

## Layers

```text
pt_agent/
|-- runtime/              Windows PT discovery and process integration
|-- compiler/             IOS command templates
|-- dsl_compiler.py       Full YAML-to-plan compilation
|-- validation.py         Schema, semantic, and command-safety checks
|-- script_backend.py     PT Script Engine JavaScript builders
|-- script_bridge.py      Local HTTP bridge
|-- dsl_deployment.py     Verification evaluation
`-- cli.py                Command adapter and deployment orchestration
```

The agent calls only the public CLI. It must not import private JavaScript
builders or bypass command validation.

## Agent-Facing Commands

Commands return JSON:

```powershell
pt-agent doctor --wait-bridge 5
pt-agent validate-dsl <file>
pt-agent compile-dsl <file>
pt-agent deploy-dsl <file>
```

The agent runs deployment in the foreground and waits for the process to
finish. The command returns the final JSON report and standard exit code.

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

- Model-facing workflows use the YAML compiler and CommandPlan allowlist.
- Raw JavaScript and arbitrary IOS command execution are not public commands.
- Each deployment produces a PKT, JSON report, and JSONL audit log.
- Test expectations must not be weakened just to obtain a passing report.

## Skill

The operational skill is:

```text
skills/pt-network-automation/SKILL.md
```

It defines the doctor -> validate -> compile -> deploy workflow and routes
failure diagnosis to the troubleshooting playbook.

## Future Optional Integration

If a later product requires MCP or another transport, add a thin adapter over
the same CLI operations. The compiler, validation, and runtime do not need to
move.
