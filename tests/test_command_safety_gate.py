from __future__ import annotations

import unittest
from contextlib import redirect_stderr
from io import StringIO

from pt_agent.cli import _run_ios_cli
from pt_agent.validation import CommandSafetyError


class _AuditStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def record(self, event: str, **fields: object) -> None:
        self.events.append((event, fields))


class CommandSafetyGateTests(unittest.TestCase):
    def test_cli_gate_blocks_before_bridge_dispatch_and_logs(self) -> None:
        audit = _AuditStub()
        with redirect_stderr(StringIO()):
            with self.assertRaises(CommandSafetyError):
                _run_ios_cli(
                    None,  # type: ignore[arg-type]
                    audit,  # type: ignore[arg-type]
                    label="unsafe",
                    device="R1",
                    commands=["write erase"],
                    timeout=1.0,
                )
        self.assertEqual(audit.events[0][0], "command_blocked")
        event = audit.events[0][1]
        self.assertEqual(event["device"], "R1")
        self.assertEqual(event["commands"], ["write erase"])
        self.assertTrue(event["issues"])


if __name__ == "__main__":
    unittest.main()
