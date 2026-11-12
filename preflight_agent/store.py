"""Completed trace storage with digest verification and exclusive atomic publication."""
import json
import os
import re
import tempfile
from pathlib import Path

from preflight_agent.common import canonical, digest


class ReplayMismatch(ValueError):
    """An identity has already been bound to different inputs."""


class TraceCorrupt(ValueError):
    """Stored trace failed integrity checks; manual inspection is required."""


class TraceStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, workflow_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", workflow_id):
            raise ValueError("invalid workflow_id")
        return self.root / (workflow_id + ".json")

    def load(self, workflow_id: str, inputs_digest: str) -> dict | None:
        path = self.path(workflow_id)
        if path.is_symlink():
            raise TraceCorrupt("trace symlink forbidden")
        if not path.exists():
            return None
        try:
            trace = json.loads(path.read_text(encoding="utf-8"))
            sealed = {k: v for k, v in trace.items() if k != "trace_digest"}
            if trace.get("trace_digest") != digest(sealed) or trace.get("workflow_id") != workflow_id:
                raise ValueError("integrity mismatch")
        except (ValueError, OSError, AttributeError) as exc:
            raise TraceCorrupt("stored trace integrity check failed") from exc
        if trace.get("inputs_digest") != inputs_digest:
            raise ReplayMismatch("workflow_id already bound to different inputs")
        return trace

    def save(self, trace: dict) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        trace = {**trace, "trace_digest": digest(trace)}
        fd, name = tempfile.mkstemp(prefix=".trace-", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical(trace) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, self.path(trace["workflow_id"]))
            except FileExistsError:
                return self.load(trace["workflow_id"], trace["inputs_digest"])
        finally:
            temporary.unlink(missing_ok=True)
        return trace
