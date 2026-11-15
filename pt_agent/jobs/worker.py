"""Detached worker for one persisted Packet Tracer deployment job."""

from __future__ import annotations

import argparse
from pathlib import Path

from .manager import JobManager, JobOptions, WorkspaceJobLock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("data_root", type=Path)
    parser.add_argument("workspace_root", type=Path)
    args = parser.parse_args(argv)

    manager = JobManager(
        workspace_root=args.workspace_root,
        data_root=args.data_root,
        recover=False,
        in_process=False,
    )
    job = manager.get(args.job_id)
    if job is None:
        raise FileNotFoundError(f"job not found: {args.job_id}")
    options = JobOptions(**job["options"])
    job.update(
        stage="waiting_for_pt_slot",
        progress=1,
        updated_at=_worker_timestamp(),
    )
    manager._write_job(job)
    lock = WorkspaceJobLock(
        args.workspace_root / ".pt-agent-job.lock"
    )
    try:
        if not lock.acquire(timeout=options.max_runtime):
            raise TimeoutError("timed out waiting for the PT execution lock")
        manager.run_existing(args.job_id)
    except TimeoutError as exc:
        job = manager.get(args.job_id)
        if job is not None:
            job.update(
                status="timed_out",
                stage="timed_out",
                progress=100,
                finished_at=_worker_timestamp(),
                updated_at=_worker_timestamp(),
                error=str(exc),
            )
            manager._write_job(job)
        raise
    except Exception as exc:
        job = manager.get(args.job_id)
        if job is not None and job.get("status") not in {
            "passed",
            "failed",
            "cancelled",
            "timed_out",
        }:
            job.update(
                status="failed",
                stage="worker_error",
                progress=100,
                finished_at=_worker_timestamp(),
                updated_at=_worker_timestamp(),
                error=f"{type(exc).__name__}: {exc}",
            )
            manager._write_job(job)
        raise
    finally:
        lock.release()
    return 0


def _worker_timestamp() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
