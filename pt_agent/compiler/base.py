"""Shared command-plan primitives for deterministic IOS rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pt_agent.validation import CommandSafetyValidator, ValidationIssue


class CommandCompileError(ValueError):
    """Structured input cannot be compiled into a safe command plan."""


@dataclass(frozen=True)
class CommandPlan:
    device: str
    module: str
    commands: tuple[str, ...]

    def as_list(self) -> list[str]:
        return list(self.commands)

    def safety_issues(self) -> list[ValidationIssue]:
        return CommandSafetyValidator().validate(self.commands)

    def validate(self) -> None:
        issues = self.safety_issues()
        if issues:
            details = "; ".join(
                f"{issue.code} at {issue.path}: {issue.message}"
                for issue in issues
            )
            raise CommandCompileError(details)


def config_plan(
    device: str,
    module: str,
    body: Iterable[str],
    *,
    show_commands: Iterable[str] = (),
) -> CommandPlan:
    """Wrap configuration commands in enter/exit/save/show boilerplate."""

    commands = [
        "configure terminal",
        *body,
        "end",
        "write memory",
        *show_commands,
    ]
    plan = CommandPlan(device, module, tuple(commands))
    plan.validate()
    return plan


def require_nonempty(value: str, field: str) -> str:
    text = value.strip()
    if not text:
        raise CommandCompileError(f"{field} must not be empty")
    return text


def require_port(value: str, field: str = "port") -> str:
    text = require_nonempty(value, field)
    if any(char.isspace() for char in text):
        raise CommandCompileError(f"{field} must not contain whitespace")
    return text
