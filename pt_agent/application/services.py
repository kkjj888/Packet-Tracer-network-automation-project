"""Transport-neutral Packet Tracer network application services."""

from __future__ import annotations

import json
from pathlib import Path

from ..dsl_compiler import DslCompileError, compile_network_dsl
from ..validation import (
    DEFAULT_SCHEMA_PATH,
    NetworkValidator,
    load_yaml_document,
)


class WorkspacePathError(ValueError):
    """A requested file is outside the configured workspace."""


def resolve_workspace_file(
    workspace_root: Path,
    path: str | Path,
    *,
    must_exist: bool = True,
) -> Path:
    root = workspace_root.resolve()
    requested = Path(path).expanduser()
    resolved = (requested if requested.is_absolute() else root / requested).resolve()
    if resolved != root and root not in resolved.parents:
        raise WorkspacePathError(
            f"path must be inside workspace {root}: {resolved}"
        )
    if must_exist and not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


class NetworkValidationService:
    def __init__(
        self,
        *,
        workspace_root: Path,
        schema_path: Path = DEFAULT_SCHEMA_PATH,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.schema_path = schema_path

    def validate(self, path: str | Path) -> dict[str, object]:
        try:
            dsl_path = resolve_workspace_file(self.workspace_root, path)
            document = load_yaml_document(dsl_path)
            result = NetworkValidator(self.schema_path).validate(document)
        except Exception as exc:
            return {
                "valid": False,
                "error_count": 1,
                "warning_count": 0,
                "issues": [
                    {
                        "severity": "error",
                        "code": "DSL_LOAD_ERROR",
                        "path": "$",
                        "message": str(exc),
                    }
                ],
            }
        payload = result.to_dict()
        payload["dsl_path"] = str(dsl_path)
        return payload


class CompilationService:
    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def compile(
        self,
        path: str | Path,
        *,
        output: str | Path | None = None,
    ) -> dict[str, object]:
        try:
            dsl_path = resolve_workspace_file(self.workspace_root, path)
            document = load_yaml_document(dsl_path)
            network = compile_network_dsl(document)
        except (DslCompileError, OSError, ValueError) as exc:
            return {"compiled": False, "error": str(exc)}

        payload = network.to_dict()
        payload["compiled"] = True
        payload["dsl_path"] = str(dsl_path)
        if output is not None:
            output_path = resolve_workspace_file(
                self.workspace_root,
                output,
                must_exist=False,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            payload["output_path"] = str(output_path)
        return payload
