from __future__ import annotations

import unittest
from pathlib import Path

from pt_agent.application.services import (
    CompilationService,
    NetworkValidationService,
    WorkspacePathError,
    resolve_workspace_file,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT_CASE = (
    PROJECT_ROOT / "examples" / "assignment" / "uc01-ripv2-triangle.yaml"
)


class NetworkApplicationServiceTests(unittest.TestCase):
    def test_validation_service_returns_structured_result(self) -> None:
        result = NetworkValidationService(
            workspace_root=PROJECT_ROOT
        ).validate(ASSIGNMENT_CASE)
        self.assertTrue(result["valid"])
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(
            Path(str(result["dsl_path"])),
            ASSIGNMENT_CASE.resolve(),
        )

    def test_compilation_service_returns_compiled_plan(self) -> None:
        result = CompilationService(
            workspace_root=PROJECT_ROOT
        ).compile(ASSIGNMENT_CASE)
        self.assertTrue(result["compiled"])
        self.assertTrue(result["command_plans"])
        self.assertEqual(result["project"], "uc01-ripv2-triangle")

    def test_workspace_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(WorkspacePathError):
            resolve_workspace_file(
                PROJECT_ROOT,
                PROJECT_ROOT.parent / "outside.yaml",
                must_exist=False,
            )


if __name__ == "__main__":
    unittest.main()
