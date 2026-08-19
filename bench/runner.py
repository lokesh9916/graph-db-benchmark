"""Benchmark harness.

Usage:
    python -m bench.runner --db cognodb --phase all
    python -m bench.runner --db cognodb --phase reads
    python -m bench.runner --db cognodb --phase mixed --concurrency 10

Phases: load, reads, mixed, footprint, all
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .adapters import ALL_ADAPTERS, get_adapter
from .config import CFG
from .metrics import LatencySample, Timer, dump_summary, write_jsonl
from .workloads import READ_WORKLOADS, WorkloadName


def _load_dataset() -> tuple[list[int], list[tuple[int, int]]]:
    nodes_path = CFG.dataset_dir / "nodes.csv"
    edges_path = CFG.dataset_dir / "edges.csv"
    if not nodes_path.exists() or not edges_path.exists():
        raise FileNotFoundError(
            f"Dataset not found under {CFG.dataset_dir}. "
            f"Run `python -m data.download_and_sample` first."
        )
    ids: list[int] = []
    with nodes_path.open() as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            ids.append(int(row[0]))
    edges: list[tuple[int, int]] = []
    with edges_path.open() as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            edges.append((int(row[0]), int(row[1])))
    return ids, edges


def phase_load(adapter, ids, edges, results_dir: Path) -> dict:
    print(f"[{adapter.name}] resetting schema...")
    adapter.reset_schema()

    print(f"[{adapter.name}] loading {len(ids):,} nodes...")
    t0 = time.perf_counter()
    nps = adapter.load_nodes(ids)
    node_secs = time.perf_counter() - t0

    print(f"[{adapter.name}] loading {len(edges):,} edges...")
    t1 = time.perf_counter()
    rps = adapter.load_edges(edges)
    edge_secs = time.perf_counter() - t1

    record = {
        "db": adapter.name,
        "phase": "load",
        "nodes": len(ids),
        "edges": len(edges),
        "nodes_per_sec": nps,
        "rels_per_sec": rps,
        "load_wallclock_s": node_secs + edge_secs,
        "node_load_s": node_secs,
        "edge_load_s": edge_secs,
    }
    write_jsonl(results_dir / f"{adapter.name}.jsonl", record)
    return record


def phase_reads(adapter, ids, results_dir: Path, rng: random.Random) -> list[dict]:
    id_min, id_max = min(ids), max(ids)
    summaries: list[dict] = []

    for w in READ_WORKLOADS:
        # Warm-up
        for _ in range(CFG.warmup):
            _sample_and_run(adapter, w, ids, id_min, id_max, rng)

        # Measure
        sample = LatencySample(workload=w, db=adapter.name)
        for _ in tqdm(range(CFG.iterations), desc=f"[{adapter.name}] {w}"):
            with Timer() as t:
                _sample_and_run(adapter, w, ids, id_min, id_max, rng)
            sample.add(t.elapsed_ms)

        s = sample.summary()
        summaries.append(s)
        write_jsonl(results_dir / f"{adapter.name}.jsonl", {"phase": "reads", **s})
    return summaries


def _sample_and_run(adapter, workload: str, ids, id_min: int, id_max: int, rng: random.Random):
    if workload == WorkloadName.INDEXED:
        lo = rng.randint(id_min, id_max - 100)
        return adapter.run_read(workload, {"lo": lo, "hi": lo + 100})
    if workload == WorkloadName.AGG:
        return adapter.run_read(workload, {})
    node_id = ids[rng.randrange(len(ids))]
    return adapter.run_read(workload, {"id": node_id})


def phase_mixed(adapter, ids, results_dir: Path, rng: random.Random) -> list[dict]:
    """Sustained read/write throughput across concurrency levels."""
    id_min, id_max = min(ids), max(ids)
    read_pct = CFG.rw_read_pct / 100.0
    duration = CFG.mixed_duration_s
    summaries: list[dict] = []

    for c in CFG.concurrency_levels:
        stop_at = time.perf_counter() + duration
        counters = {"ops": 0, "reads": 0, "writes": 0, "errors": 0}
        lats: list[float] = []

        def worker(seed: int):
            local_rng = random.Random(seed)
            ops = 0
            while time.perf_counter() < stop_at:
                is_read = local_rng.random() < read_pct
                try:
                    with Timer() as t:
                        if is_read:
                            node_id = ids[local_rng.randrange(len(ids))]
                            adapter.run_read(WorkloadName.HOP1, {"id": node_id})
                        else:
                            a = local_rng.randint(id_min, id_max)
                            b = local_rng.randint(id_min, id_max)
                            adapter.run_write({"a": a, "b": b})
                    lats.append(t.elapsed_ms)
                    counters["reads" if is_read else "writes"] += 1
                    counters["ops"] += 1
                except Exception:
                    counters["errors"] += 1
                ops += 1
            return ops

        with ThreadPoolExecutor(max_workers=c) as ex:
            futs = [ex.submit(worker, CFG.seed + i) for i in range(c)]
            for _ in as_completed(futs):
                pass

        import numpy as np
        arr = np.array(lats) if lats else np.array([0.0])
        summary = {
            "phase": "mixed",
            "db": adapter.name,
            "concurrency": c,
            "read_pct": CFG.rw_read_pct,
            "duration_s": duration,
            "ops": counters["ops"],
            "reads": counters["reads"],
            "writes": counters["writes"],
            "errors": counters["errors"],
            "throughput_qps": counters["ops"] / duration,
            "p50_ms": float(np.percentile(arr, 50)),
            "p95_ms": float(np.percentile(arr, 95)),
        }
        summaries.append(summary)
        write_jsonl(results_dir / f"{adapter.name}.jsonl", summary)
        print(f"[{adapter.name}] mixed c={c}: {summary['throughput_qps']:.1f} qps "
              f"(errors={counters['errors']})")
    return summaries


def phase_footprint(adapter, results_dir: Path) -> dict:
    fp = adapter.observable_footprint()
    record = {"phase": "footprint", "db": adapter.name, **fp}
    write_jsonl(results_dir / f"{adapter.name}.jsonl", record)
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, choices=ALL_ADAPTERS)
    ap.add_argument("--phase", default="all",
                    choices=["load", "reads", "mixed", "footprint", "all"])
    ap.add_argument("--results", default="results/raw")
    args = ap.parse_args()

    results_dir = Path(args.results)
    rng = random.Random(CFG.seed)

    ids, edges = _load_dataset()
    print(f"Dataset: {len(ids):,} nodes, {len(edges):,} edges")

    adapter = get_adapter(args.db)
    with adapter:
        collected: dict = {"db": adapter.name}

        if args.phase in ("load", "all"):
            collected["load"] = phase_load(adapter, ids, edges, results_dir)

        if args.phase in ("reads", "all"):
            collected["reads"] = phase_reads(adapter, ids, results_dir, rng)

        if args.phase in ("mixed", "all"):
            collected["mixed"] = phase_mixed(adapter, ids, results_dir, rng)

        if args.phase in ("footprint", "all"):
            collected["footprint"] = phase_footprint(adapter, results_dir)

    summary_path = Path("results/report") / f"{args.db}.summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(collected, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
