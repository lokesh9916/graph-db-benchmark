from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    v = os.getenv(name)
    return int(v) if v else default


def _int_list(name: str, default: list[int]) -> list[int]:
    v = os.getenv(name)
    if not v:
        return default
    return [int(x.strip()) for x in v.split(",") if x.strip()]


@dataclass
class BenchConfig:
    dataset_dir: Path = Path(os.getenv("BENCH_DATASET", "data/processed/pokec_200k"))
    iterations: int = _int("BENCH_ITERATIONS", 100)
    warmup: int = _int("BENCH_WARMUP", 20)
    concurrency_levels: list[int] = field(default_factory=lambda: _int_list("BENCH_CONCURRENCY", [1, 10, 40]))
    rw_read_pct: int = _int("BENCH_RW_MIX", 80)
    seed: int = _int("BENCH_SEED", 42)
    mixed_duration_s: int = _int("BENCH_MIXED_DURATION_S", 30)


CFG = BenchConfig()


# Per-DB connection info (only read when that adapter is used)
def cognodb_env() -> dict[str, str]:
    return {
        "uri": os.environ["COGNODB_URI"],
        "user": os.getenv("COGNODB_USER", "cognodb"),
        "password": os.environ["COGNODB_PASSWORD"],
    }


def neo4j_env() -> dict[str, str]:
    return {
        "uri": os.environ["NEO4J_URI"],
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "password": os.environ["NEO4J_PASSWORD"],
    }


def memgraph_env() -> dict[str, str]:
    return {
        "uri": os.environ["MEMGRAPH_URI"],
        "user": os.getenv("MEMGRAPH_USER", ""),
        "password": os.getenv("MEMGRAPH_PASSWORD", ""),
    }


def arango_env() -> dict[str, str]:
    return {
        "url": os.environ["ARANGO_URL"],
        "db": os.getenv("ARANGO_DB", "benchmark"),
        "user": os.getenv("ARANGO_USER", "root"),
        "password": os.environ["ARANGO_PASSWORD"],
    }


def janus_env() -> dict[str, str]:
    return {"url": os.getenv("JANUS_URL", "ws://localhost:8182/gremlin")}
