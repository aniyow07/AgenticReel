"""Per-job logging: run_log.jsonl, cost_report.csv and interventions.md."""
from __future__ import annotations

import csv
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

COST_FIELDS = ["timestamp", "stage", "provider", "model", "prompt_tokens", "completion_tokens", "total_tokens",
               "cost", "currency", "cost_basis", "status"]

_SECRET_PATTERNS = [re.compile(r"sk-or-[A-Za-z0-9\-_]{10,}"), re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{10,}")]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact(value):
    """Strip anything that looks like an API key from log payloads."""
    if isinstance(value, str):
        for p in _SECRET_PATTERNS:
            value = p.sub("[REDACTED]", value)
        return value
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if "api_key" in k.lower() or k.lower() == "authorization" else redact(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class RunLogger:
    def __init__(self, job_id: str, logs_dir: Path):
        self.job_id = job_id
        self.dir = Path(logs_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.run_log = self.dir / "run_log.jsonl"
        self.cost_csv = self.dir / "cost_report.csv"
        self.interventions = self.dir / "interventions.md"
        self._lock = threading.Lock()
        if not self.cost_csv.exists():
            with open(self.cost_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(COST_FIELDS)

    def log(self, stage: str, tool: str, status: str, **fields) -> dict:
        entry = {"timestamp": now_iso(), "job_id": self.job_id, "stage": stage, "tool": tool, "status": status}
        entry.update(fields)
        entry = redact(entry)
        with self._lock, open(self.run_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def cost(self, stage: str, provider: str, model: str, usage: dict | None, cost: float | None,
             cost_basis: str, status: str) -> None:
        usage = usage or {}
        row = [now_iso(), stage, provider, model, usage.get("prompt_tokens", ""), usage.get("completion_tokens", ""),
               usage.get("total_tokens", ""), "" if cost is None else f"{cost:.6f}", "USD", cost_basis, status]
        with self._lock, open(self.cost_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def intervention(self, stage: str, action: str, reason: str, who: str = "user") -> None:
        new = not self.interventions.exists()
        with self._lock, open(self.interventions, "a", encoding="utf-8") as f:
            if new:
                f.write("# Interventions\n\n| Timestamp | Who | Stage | Action | Reason |\n|---|---|---|---|---|\n")
            clean = lambda s: str(s).replace("|", "/").replace("\n", " ")  # noqa: E731
            f.write(f"| {now_iso()} | {clean(who)} | {clean(stage)} | {clean(action)} | {clean(reason)} |\n")

    def entries(self) -> list[dict]:
        if not self.run_log.exists():
            return []
        out = []
        for line in self.run_log.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def total_cost(self) -> float:
        total = 0.0
        if not self.cost_csv.exists():
            return 0.0
        with open(self.cost_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    total += float(row["cost"]) if row["cost"] else 0.0
                except ValueError:
                    pass
        return total
