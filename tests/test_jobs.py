from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from pt_agent.jobs import JobManager, JobOptions
from pt_agent.jobs.manager import WorkspaceJobLock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT_CASE = (
    PROJECT_ROOT / "examples" / "assignment" / "uc01-ripv2-triangle.yaml"
)


class JobManagerTests(unittest.TestCase):
    def test_workspace_lock_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / ".pt-agent-job.lock"
            first = WorkspaceJobLock(lock_path)
            second = WorkspaceJobLock(lock_path)
            try:
                self.assertTrue(first.acquire(timeout=1))
                self.assertFalse(second.acquire(timeout=0.1))
                first.release()
                self.assertTrue(second.acquire(timeout=1))
            finally:
                first.release()
                second.release()

    def test_in_process_job_persists_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary) / "jobs"

            def command_builder(
                dsl_path: Path,
                run_dir: Path,
                options: JobOptions,
            ) -> list[str]:
                del dsl_path, options
                script = (
                    "import json, pathlib, sys; "
                    "run=pathlib.Path(sys.argv[1]); "
                    "report=run/'fake-project.json'; "
                    "report.write_text(json.dumps({'status':'passed'}), encoding='utf-8'); "
                    "(run/'fake-project.pkt').write_bytes(b'pkt'); "
                    "(run/'fake-project-audit.jsonl').write_text('{}\\n', encoding='utf-8')"
                )
                return [sys.executable, "-c", script, str(run_dir)]

            manager = JobManager(
                workspace_root=PROJECT_ROOT,
                data_root=data_root,
                command_builder=command_builder,
            )
            try:
                job = manager.start(ASSIGNMENT_CASE)
                completed = self._wait_for_terminal(manager, str(job["job_id"]))
            finally:
                manager.shutdown()

            self.assertEqual(completed["status"], "passed")
            self.assertTrue(Path(str(completed["report_path"])).is_file())
            self.assertTrue(Path(str(completed["project_path"])).is_file())
            self.assertTrue(Path(str(completed["audit_path"])).is_file())
            result = manager.result(str(job["job_id"]))
            self.assertEqual(result["report"]["status"], "passed")

    def test_running_job_can_be_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = JobManager(
                workspace_root=PROJECT_ROOT,
                data_root=Path(temporary) / "jobs",
                command_builder=lambda dsl, run, options: [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(30)",
                ],
            )
            try:
                job = manager.start(ASSIGNMENT_CASE)
                job_id = str(job["job_id"])
                self._wait_for_running(manager, job_id)
                manager.cancel(job_id)
                completed = self._wait_for_terminal(manager, job_id)
            finally:
                manager.shutdown()
            self.assertEqual(completed["status"], "cancelled")

    def _wait_for_running(
        self,
        manager: JobManager,
        job_id: str,
        timeout: float = 10.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = manager.get(job_id)
            if job is not None and job.get("status") == "running":
                return job
            time.sleep(0.05)
        self.fail("job did not enter running state")

    def _wait_for_terminal(
        self,
        manager: JobManager,
        job_id: str,
        timeout: float = 15.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        terminal = {"passed", "failed", "cancelled", "timed_out"}
        while time.monotonic() < deadline:
            job = manager.get(job_id)
            if job is not None and job.get("status") in terminal:
                return job
            time.sleep(0.05)
        self.fail("job did not reach a terminal state")


if __name__ == "__main__":
    unittest.main()
