"""Pluggable, deterministic evidence-gathering tools.

A tool reads local data and returns observations. Tools run in order and may
use evidence gathered by earlier tools (e.g. the diff tool needs the deploy).
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .models import Evidence, EvidenceKind, Task


class Tool(Protocol):
    name: str

    def run(self, task: Task, prior: Sequence[Evidence]) -> list[Evidence]: ...


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; timestamps without a zone are taken as UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def find_deploy(evidence: Sequence[Evidence]) -> Evidence | None:
    return next((e for e in evidence if e.source == DeployLogTool.name), None)


class DeployLogTool:
    """Finds the most recent deploy of the task's service in a JSON-lines log."""

    name = "deploy_log"

    def __init__(self, path: Path) -> None:
        self.path = path

    def run(self, task: Task, prior: Sequence[Evidence]) -> list[Evidence]:
        deploys = [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]
        matching = [d for d in deploys if d["service"] == task.service]
        if not matching:
            return []
        latest = max(matching, key=lambda d: parse_timestamp(d["timestamp"]))
        return [
            Evidence(
                id=f"deploy:{task.service}:{latest['version']}",
                kind=EvidenceKind.OBSERVATION,
                source=self.name,
                summary=(
                    f"{task.service} {latest['version']} (commit {latest['commit']}) "
                    f"deployed at {latest['timestamp']}"
                ),
                data=dict(latest),
            )
        ]


class MetricsTool:
    """Reads per-request latency/status samples for the task's service from CSV."""

    name = "metrics"

    def __init__(self, path: Path) -> None:
        self.path = path

    def services(self) -> set[str]:
        with self.path.open(newline="") as f:
            return {row["service"] for row in csv.DictReader(f)}

    def run(self, task: Task, prior: Sequence[Evidence]) -> list[Evidence]:
        with self.path.open(newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["service"] == task.service]
        if not rows:
            return []
        samples = [
            {
                "timestamp": r["timestamp"],
                "latency_ms": float(r["latency_ms"]),
                "status": int(r["status"]),
            }
            for r in rows
        ]
        return [
            Evidence(
                id=f"metrics:{task.service}",
                kind=EvidenceKind.OBSERVATION,
                source=self.name,
                summary=(
                    f"{len(samples)} request samples for {task.service} from "
                    f"{samples[0]['timestamp']} to {samples[-1]['timestamp']}"
                ),
                data={"samples": samples},
            )
        ]


_DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)


class DiffTool:
    """Reads the code change for the deployed commit and lists the files it touched."""

    name = "diff"

    def __init__(self, changes_dir: Path) -> None:
        self.changes_dir = changes_dir

    def run(self, task: Task, prior: Sequence[Evidence]) -> list[Evidence]:
        deploy = find_deploy(prior)
        if deploy is None:
            return []
        commit = str(deploy.data["commit"])
        if not re.fullmatch(r"[0-9a-f]{7,40}", commit):
            return []
        path = self.changes_dir / f"{commit}.diff"
        if not path.is_file():
            return []
        text = path.read_text()
        # Both sides of each header, so deleted and renamed files are included.
        files = list(dict.fromkeys(p for pair in _DIFF_HEADER.findall(text) for p in pair))
        return [
            Evidence(
                id=f"diff:{commit}",
                kind=EvidenceKind.OBSERVATION,
                source=self.name,
                summary=f"commit {commit} changed {len(files)} file(s): {', '.join(files)}",
                data={"commit": commit, "files_changed": files, "diff": text},
            )
        ]


def local_tools(evidence_dir: Path) -> tuple[MetricsTool, list[Tool]]:
    """The standard tool set for an evidence directory, in run order."""
    metrics = MetricsTool(evidence_dir / "metrics.csv")
    tools: list[Tool] = [
        DeployLogTool(evidence_dir / "deploys.jsonl"),
        metrics,
        DiffTool(evidence_dir / "changes"),
    ]
    return metrics, tools
