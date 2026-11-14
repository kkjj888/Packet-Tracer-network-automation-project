"""Windows-only Packet Tracer installation and process integration."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class PacketTracerInstallation:
    root: Path
    executable: Path


class WindowsPacketTracerRuntime:
    """Discover and launch the local Windows Packet Tracer installation."""

    def __init__(
        self,
        project_root: Path,
        *,
        pt_root: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.environment = dict(os.environ if environment is None else environment)
        self.requested_root = (
            Path(pt_root).expanduser()
            if pt_root is not None
            else (
                Path(self.environment["PT_AGENT_PT_ROOT"]).expanduser()
                if self.environment.get("PT_AGENT_PT_ROOT")
                else None
            )
        )

    @property
    def script_module(self) -> Path:
        return (
            self.project_root / "vendor" / "mcp-bridge.pts"
        ).resolve()

    def discover(self) -> PacketTracerInstallation | None:
        for root in self._candidate_roots():
            executable = (root / "bin" / "PacketTracer.exe").resolve()
            if executable.is_file():
                return PacketTracerInstallation(root.resolve(), executable)
        return None

    def doctor(self) -> dict[str, object]:
        installation = self.discover()
        errors: list[str] = []
        if not sys.platform.startswith("win"):
            errors.append(
                "Packet Tracer runtime is currently supported only on Windows"
            )
        if installation is None:
            errors.append("PacketTracer.exe was not found")
        if not self.script_module.is_file():
            errors.append(f"Script Module not found: {self.script_module}")
        return {
            "platform": sys.platform,
            "runtime_supported": sys.platform.startswith("win"),
            "pt_root": (
                str(installation.root)
                if installation is not None
                else (
                    str(self.requested_root.resolve())
                    if self.requested_root is not None
                    else None
                )
            ),
            "pt_executable": (
                str(installation.executable)
                if installation is not None
                else None
            ),
            "script_module": str(self.script_module),
            "script_module_available": self.script_module.is_file(),
            "pt_installed": installation is not None,
            "validation_errors": errors,
        }

    def launch(self) -> subprocess.Popen[bytes]:
        if not sys.platform.startswith("win"):
            raise OSError("Packet Tracer runtime is currently Windows-only")
        installation = self.discover()
        if installation is None:
            raise FileNotFoundError("PacketTracer.exe was not found")
        return subprocess.Popen(
            [str(installation.executable)],
            cwd=str(installation.executable.parent),
        )

    def _candidate_roots(self) -> list[Path]:
        candidates: list[Path] = []
        if self.requested_root is not None:
            candidates.append(self.requested_root)

        for configured in (
            r"D:\Cisco Packet Tracer 9.0.1",
            r"C:\Program Files\Cisco Packet Tracer 9.0.1",
            r"C:\Program Files (x86)\Cisco Packet Tracer 9.0.1",
        ):
            candidates.append(Path(configured))

        for base in (
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
            Path("D:\\"),
        ):
            if not base.is_dir():
                continue
            try:
                candidates.extend(
                    sorted(
                        (
                            item
                            for item in base.glob("Cisco Packet Tracer*")
                            if item.is_dir()
                        ),
                        reverse=True,
                    )
                )
            except OSError:
                continue

        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = os.path.normcase(str(candidate))
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique
