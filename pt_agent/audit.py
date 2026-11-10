"""Append-only JSON Lines audit logging."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonlAuditLogger:
    def __init__(self, path: Path, run_id: str, *, reset: bool = True) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._seq = 0
        if reset:
            self.path.write_text("", encoding="utf-8")

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        self._seq += 1
        payload: dict[str, Any] = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "seq": self._seq,
            "event": event,
        }
        payload.update(fields)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return payload

