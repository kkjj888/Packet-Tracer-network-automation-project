# Command Safety and Hard Isolation

This project uses fail-closed command handling. A command must match the
supported allowlist and must not match a destructive-command rule before it
can reach Packet Tracer.

## Enforcement Layers

```text
YAML Schema
-> network semantics
-> deterministic command compiler
-> allowlist
-> dangerous-command blacklist
-> execution gateway
-> JSONL audit
```

The command gateway validates the complete command sequence again immediately
before the first IOS command is dispatched. A blocked sequence never reaches
the target device.

Validate commands without executing them:

```powershell
python -m pt_agent check-commands "reload"
python -m pt_agent check-commands "do write erase"
python -m pt_agent check-commands "show ip route"
```

The command exits with a nonzero status when any string is rejected.

## Dangerous Command Categories

### Device Restart

```text
reload
reload in <time>
reload at <time>
rel
do reload
```

### Configuration Destruction

```text
write erase
wr er
erase startup-config
erase nvram:
configure replace ...
archive restore ...
archive rollback ...
```

### Filesystem Destruction

```text
format
delete
copy ...
rename ...
mkdir ...
rmdir ...
```

### Boot and Low-Level Control

```text
boot ...
config-register ...
confreg ...
```

### Security and Audit Removal

```text
crypto key zeroize ...
crypto key delete ...
no aaa ...
no access-group ...
no access-class ...
no logging ...
no service password-encryption
```

### Arbitrary Execution

```text
tclsh
run ...
exec ...
system ...
bash ...
sh ...
```

### Operational Disruption

```text
debug ...
clear ...
shutdown
no ip routing
```

`no shutdown` remains allowed because it is a required, non-destructive
interface enable operation.

## Input Hardening

The command gateway rejects:

- newlines and multi-command strings
- control characters and NUL bytes
- shell-like injection tokens
- commands with a leading `do` that hide a blocked command
- abbreviated forms of blocked commands
- commands outside the regex allowlist

Read-only filters such as the following remain valid:

```text
show running-config | include reload
show logging | include delete
```

The blocked word appears only in a read-only output filter, not in an
executable position.

## Controlled Reset Instead of Raw Destruction

Do not expose raw `reload`, `erase`, or `delete` commands to an LLM. If a
project needs reset or rollback, add a higher-level operation such as:

```text
reset_generated_project()
restore_checkpoint()
recreate_device()
```

Those operations should save a recovery point, validate the exact target,
record an audit event, and require an explicit confirmation policy.

## Audit Evidence

A blocked command writes an append-only `command_blocked` event containing:

- audit label and device
- complete rejected command sequence
- machine-readable validation issue codes
- human-readable rejection reasons

Normal dispatches continue to record the original JavaScript expression,
command output and verification results.

## Test Coverage

The safety suite checks:

- reload and abbreviated reload
- startup configuration erase
- filesystem format and delete
- boot/configuration-register changes
- arbitrary execution shells
- security-policy removal
- hidden destructive commands after `do`
- control-character injection
- raw command entrypoint rejection
- pre-dispatch audit logging
- read-only `show` filters that mention dangerous words
