"""Persistent, serialized execution of long-running deployment jobs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping

from ..application.services import resolve_workspace_file


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class JobOptions:
    bridge_port: int = 54321
    result_timeout: float = 180.0
    connect_timeout: float = 60.0
    cli_timeout: float = 120.0
    ping_timeout: float = 30.0
    traceroute_timeout: float = 45.0
    save_timeout: float = 60.0
    convergence_rounds: int = 3
    max_runtime: float = 1800.0


CommandBuilder = Callable[[Path, Path, JobOptions], list[str]]


class JobManager:
    """Run PT mutations serially and persist queryable job state."""

    def __init__(
        self,
        *,
        workspace_root: Path,
        data_root: Path,
        python_executable: str | None = None,
        environment: Mapping[str, str] | None = None,
        command_builder: CommandBuilder | None = None,
        recover: bool = True,
        in_process: bool = True,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.data_root = data_root.resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.python_executable = python_executable or sys.executable
        self.environment = dict(os.environ if environment is None else environment)
        self.command_builder = command_builder or self._build_deploy_command
        self._executor = (
            ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="pt-deploy-job",
            )
            if in_process
            else None
        )
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        if recover:
            self._recover_interrupted_jobs()

    def start(
        self,
        dsl_path: str | Path,
        *,
        options: JobOptions | None = None,
        detached: bool = False,
    ) -> dict[str, object]:
        selected = options or JobOptions()
        source = resolve_workspace_file(self.workspace_root, dsl_path)
        job_id = time.strftime("job-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        run_dir = self.data_root / job_id
        run_dir.mkdir(parents=True, exist_ok=False)
        created = _timestamp()
        job: dict[str, object] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "created_at": created,
            "updated_at": created,
            "started_at": None,
            "finished_at": None,
            "dsl_path": str(source),
            "run_dir": str(run_dir),
            "pid": None,
            "exit_code": None,
            "report_path": None,
            "project_path": None,
            "audit_path": None,
            "stdout_path": str(run_dir / "stdout.log"),
            "stderr_path": str(run_dir / "stderr.log"),
            "error": None,
            "options": asdict(selected),
        }
        self._write_json(run_dir / "request.json", job)
        self._write_json(run_dir / "job.json", job)
        self._cancel_events[job_id] = threading.Event()
        if detached:
            worker = self._launch_worker(job_id)
            job.update(worker_pid=worker.pid, updated_at=_timestamp())
            self._write_job(job)
        else:
            if self._executor is None:
                raise RuntimeError("in-process worker is disabled")
            self._executor.submit(self._execute, job_id, source, run_dir, selected)
        return job

    def run_existing(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            raise FileNotFoundError(f"job not found: {job_id}")
        options_payload = job.get("options")
        if not isinstance(options_payload, dict):
            raise ValueError("job options are missing")
        options = JobOptions(**options_payload)
        self._execute(
            job_id,
            Path(str(job["dsl_path"])),
            Path(str(job["run_dir"])),
            options,
        )

    def list_jobs(self) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        for path in self.data_root.glob("job-*/job.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                jobs.append(payload)
        return sorted(
            jobs,
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )

    def get(self, job_id: str) -> dict[str, object] | None:
        path = self._job_path(job_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def result(self, job_id: str) -> dict[str, object] | None:
        job = self.get(job_id)
        if job is None:
            return None
        result = dict(job)
        result["report"] = self._read_optional_json(job.get("report_path"))
        return result

    def cancel(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            if job.get("status") in {"passed", "failed", "cancelled", "timed_out"}:
                return job
            event = self._cancel_events.setdefault(job_id, threading.Event())
            event.set()
            process = self._processes.get(job_id)
            if process is None or process.poll() is not None:
                for key in ("deploy_pid", "worker_pid"):
                    self._terminate_pid(job.get(key))
                job.update(
                    status="cancelled",
                    stage="cancelled",
                    progress=100,
                    finished_at=_timestamp(),
                    updated_at=_timestamp(),
                )
                self._write_job(job)
            return job

    def shutdown(self, *, wait: bool = True) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=wait, cancel_futures=True)

    def _execute(
        self,
        job_id: str,
        dsl_path: Path,
        run_dir: Path,
        options: JobOptions,
    ) -> None:
        event = self._cancel_events.setdefault(job_id, threading.Event())
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return
            if event.is_set():
                job.update(
                    status="cancelled",
                    stage="cancelled",
                    finished_at=_timestamp(),
                    updated_at=_timestamp(),
                )
                self._write_job(job)
                return
            job.update(
                status="running",
                stage="starting",
                progress=5,
                started_at=_timestamp(),
                updated_at=_timestamp(),
            )
            self._write_job(job)

        command = self.command_builder(dsl_path, run_dir, options)
        stdout_path = run_dir / "stdout.log"
        stderr_path = run_dir / "stderr.log"
        process: subprocess.Popen[bytes] | None = None
        cancelled = False
        timed_out = False

        try:
            with (
                stdout_path.open("wb") as stdout,
                stderr_path.open("wb") as stderr,
            ):
                process = subprocess.Popen(
                    command,
                    cwd=str(self.workspace_root),
                    env=self.environment,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                )
                with self._lock:
                    self._processes[job_id] = process
                    job = self.get(job_id) or {}
                    job.update(
                        stage="deploying",
                        progress=15,
                        pid=process.pid,
                        deploy_pid=process.pid,
                        updated_at=_timestamp(),
                    )
                    self._write_job(job)

                deadline = time.monotonic() + options.max_runtime
                while process.poll() is None:
                    if event.is_set():
                        cancelled = True
                        self._terminate(process)
                        break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        self._terminate(process)
                        break
                    time.sleep(0.5)
                exit_code = process.wait()
        except Exception as exc:
            exit_code = None
            with self._lock:
                job = self.get(job_id) or {}
                job.update(
                    status="failed",
                    stage="worker_error",
                    updated_at=_timestamp(),
                    finished_at=_timestamp(),
                    error=f"{type(exc).__name__}: {exc}",
                )
                self._write_job(job)
            return
        finally:
            with self._lock:
                self._processes.pop(job_id, None)

        report_path = self._find_report(run_dir)
        report = self._read_optional_json(str(report_path) if report_path else None)
        artifacts = self._find_artifacts(run_dir)
        with self._lock:
            job = self.get(job_id) or {}
            if cancelled:
                status = "cancelled"
                stage = "cancelled"
                error = "Cancellation requested"
            elif timed_out:
                status = "timed_out"
                stage = "timed_out"
                error = f"Job exceeded {options.max_runtime:.0f}s"
            elif (
                exit_code == 0
                and isinstance(report, dict)
                and report.get("status") == "passed"
            ):
                status = "passed"
                stage = "completed"
                error = None
            else:
                status = "failed"
                stage = "completed"
                error = (
                    self._read_tail(stderr_path)
                    or self._read_tail(stdout_path)
                    or "Deployment failed"
                )
            job.update(
                status=status,
                stage=stage,
                progress=100,
                exit_code=exit_code,
                deploy_pid=None,
                finished_at=_timestamp(),
                updated_at=_timestamp(),
                report_path=str(report_path) if report_path else None,
                project_path=artifacts.get("project"),
                audit_path=artifacts.get("audit"),
                error=error,
            )
            self._write_job(job)

    def _launch_worker(self, job_id: str) -> subprocess.Popen[bytes]:
        worker_stdout = self.data_root / job_id / "worker.stdout.log"
        worker_stderr = self.data_root / job_id / "worker.stderr.log"
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        with (
            worker_stdout.open("wb") as stdout,
            worker_stderr.open("wb") as stderr,
        ):
            return subprocess.Popen(
                [
                    self.python_executable,
                    "-m",
                    "pt_agent.jobs.worker",
                    job_id,
                    str(self.data_root),
                    str(self.workspace_root),
                ],
                cwd=str(self.workspace_root),
                env=self.environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )

    def _build_deploy_command(
        self,
        dsl_path: Path,
        run_dir: Path,
        options: JobOptions,
    ) -> list[str]:
        return [
            self.python_executable,
            "-m",
            "pt_agent",
            "deploy-dsl",
            str(dsl_path),
            "--artifacts-dir",
            str(run_dir),
            "--bridge-port",
            str(options.bridge_port),
            "--result-timeout",
            str(options.result_timeout),
            "--connect-timeout",
            str(options.connect_timeout),
            "--cli-timeout",
            str(options.cli_timeout),
            "--ping-timeout",
            str(options.ping_timeout),
            "--traceroute-timeout",
            str(options.traceroute_timeout),
            "--save-timeout",
            str(options.save_timeout),
            "--convergence-rounds",
            str(options.convergence_rounds),
        ]

    def _job_path(self, job_id: str) -> Path:
        if not job_id.startswith("job-") or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
            for character in job_id.lower()
        ):
            raise ValueError(f"invalid job id: {job_id!r}")
        return self.data_root / job_id / "job.json"

    def _write_job(self, job: dict[str, object]) -> None:
        job_id = str(job.get("job_id", ""))
        run_dir = self.data_root / job_id
        if not run_dir.resolve().is_relative_to(self.data_root):
            raise ValueError("job directory escaped data root")
        run_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(run_dir / "job.json", job)

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _read_optional_json(path: object) -> object | None:
        if not path:
            return None
        try:
            return json.loads(Path(str(path)).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _read_tail(path: Path, limit: int = 4000) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text[-limit:].strip()

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    @staticmethod
    def _terminate_pid(value: object) -> None:
        try:
            pid = int(value)
        except (TypeError, ValueError):
            return
        if pid <= 0:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return

    @staticmethod
    def _find_report(run_dir: Path) -> Path | None:
        candidates = [
            path
            for path in run_dir.glob("*.json")
            if path.name not in {"job.json", "request.json"}
        ]
        return max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None

    @staticmethod
    def _find_artifacts(run_dir: Path) -> dict[str, str]:
        projects = sorted(
            run_dir.glob("*.pkt"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        audits = sorted(
            run_dir.glob("*-audit.jsonl"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return {
            "project": str(projects[0]) if projects else "",
            "audit": str(audits[0]) if audits else "",
        }

    def _recover_interrupted_jobs(self) -> None:
        for path in self.data_root.glob("job-*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(job, dict):
                continue
            if job.get("status") not in {"queued", "running"}:
                continue
            job.update(
                status="failed",
                stage="interrupted",
                updated_at=_timestamp(),
                finished_at=_timestamp(),
                error="Job was interrupted when its manager process exited",
            )
            self._write_job(job)
