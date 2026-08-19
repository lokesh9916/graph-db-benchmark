from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class LatencySample:
    workload: str
    db: str
    latency_ms: list[float] = field(default_factory=list)

    def add(self, ms: float) -> None:
        self.latency_ms.append(ms)

    def summary(self) -> dict:
        arr = np.array(self.latency_ms, dtype=float)
        if arr.size == 0:
            return {"workload": self.workload, "db": self.db, "n": 0}
        return {
            "workload": self.workload,
            "db": self.db,
            "n": int(arr.size),
            "p50_ms": float(np.percentile(arr, 50)),
            "p90_ms": float(np.percentile(arr, 90)),
            "p95_ms": float(np.percentile(arr, 95)),
            "p99_ms": float(np.percentile(arr, 99)),
            "mean_ms": float(arr.mean()),
            "min_ms": float(arr.min()),
            "max_ms": float(arr.max()),
        }


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self.t0) * 1000.0


def write_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def dump_summary(path: Path, summaries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
