from __future__ import annotations

import unittest
from pathlib import Path

from pt_agent.runtime import WindowsPacketTracerRuntime


class WindowsPacketTracerRuntimeTests(unittest.TestCase):
    def test_explicit_pt_root_is_discovered_first(self) -> None:
        runtime = WindowsPacketTracerRuntime(
            Path(r"D:\workspace"),
            pt_root=r"D:\explicit-pt",
            environment={"PT_AGENT_PT_ROOT": r"D:\environment-pt"},
        )
        roots = runtime._candidate_roots()
        self.assertEqual(roots[0], Path(r"D:\explicit-pt"))

    def test_environment_root_is_used_without_explicit_root(self) -> None:
        runtime = WindowsPacketTracerRuntime(
            Path(r"D:\workspace"),
            environment={"PT_AGENT_PT_ROOT": r"D:\environment-pt"},
        )
        roots = runtime._candidate_roots()
        self.assertEqual(roots[0], Path(r"D:\environment-pt"))

    def test_script_module_is_inside_project_vendor_directory(self) -> None:
        runtime = WindowsPacketTracerRuntime(Path(r"D:\workspace"))
        self.assertEqual(
            runtime.script_module,
            Path(r"D:\workspace\vendor\mcp-bridge.pts"),
        )


if __name__ == "__main__":
    unittest.main()
