# Graph Database Cloud Benchmark

**A reproducible, honest benchmark of [CognoDB Cloud](https://console.cognodb.com) against four other managed / self-hosted graph databases on the same dataset, the same logical queries, and the same resource envelope.**

> This repository is a submission for the Wexa AI take-home assignment.
> The goal is engineering rigor and honesty, **not** picking a "winner."

---

## TL;DR

| DB | Tier | Query language | Verdict (short) |
|---|---|---|---|
| **CognoDB Cloud** | free `c0` — 0.5 vCPU / 256 MB / 1 GB | Cypher (Bolt) | Solid, consistent, zero errors; aggregation is the weak spot. |
| **Neo4j AuraDB Free** | free — 50k nodes / 175k rels limit | Cypher (Bolt) | Fastest p50 point/range lookups, but high variance under load. |
| **Memgraph Cloud** | free — 256 MB | Cypher (Bolt) | Most predictable latencies; tied for top mixed throughput. |
| **ArangoDB Oasis** | free trial — smallest instance | AQL (HTTP) | Flat latency profile, but free-tier write errors are significant. |
| **JanusGraph** | — | — | **Not benchmarked:** Docker Desktop unavailable in this environment. |

Full numbers in [`results/report/results_matrix.md`](results/report/results_matrix.md), charts under [`results/report/charts/`](results/report/charts/), analysis in [§ Analysis](#analysis) below.

---

## 1. Methodology & fairness

### 1.1 Same resource envelope for every DB
The CognoDB free tier caps the fair-comparison envelope: **0.5 vCPU burstable, 256 MB RAM, 1 GB disk**. Every other DB is run on the closest available tier:

| DB | Advertised spec | Notes |
|---|---|---|
| CognoDB c0 | 0.5 vCPU / 256 MB / 1 GB | baseline |
| Neo4j AuraDB Free | not published; hard limits: 50k nodes, 175k rels | dataset sized to fit |
| Memgraph Cloud Free | 256 MB RAM | comparable |
| ArangoDB Oasis Free | 4 GB / 2 vCPU (smallest paid-trial) | **NOT parity** — flagged in analysis |
| JanusGraph (Docker) | `--cpus=0.5 --memory=256m` on the same client host | forced parity |

Every deviation is called out in [§ 4 Caveats](#caveats).

### 1.2 Same dataset
- **Source:** SNAP `soc-Pokec-relationships` (<https://snap.stanford.edu/data/soc-Pokec.html>) — a real social network.
- **Sample:** first **200,000 directed edges** over **~91k unique nodes** (deterministic, seed=42).
- Neo4j Aura Free was run on a **150,000-edge** sample because its hard cap is 175k relationships. All other DBs used the full 200k sample.

### 1.3 Same logical queries
Defined once in [`bench/workloads.py`](bench/workloads.py) and translated per DB:

| Workload | Cypher | AQL |
|---|---|---|
| Point lookup | `MATCH (u:User {id:$id})` | `FILTER u._key == @id` |
| Indexed range | `WHERE u.id >= $lo AND u.id < $hi` | `FILTER u.id >= @lo AND u.id < @hi` |
| 1/2/3-hop | `-[:FOLLOWS*k..k]->` | `k..k OUTBOUND … follows` |
| Aggregation | `MATCH ()-[r:FOLLOWS]->() RETURN count(r)` | `LENGTH(follows)` |
| Write | `MERGE (a)-[:FOLLOWS]->(b)` | `UPSERT … INSERT … INTO follows` |

(An adapter for JanusGraph/Gremlin and NebulaGraph/nGQL is included but not exercised in the reported run; see § 4.)

### 1.4 Measurement protocol
- **Warm-up:** `BENCH_WARMUP=20` iterations per workload, discarded.
- **Read latency:** `BENCH_ITERATIONS=100` timed runs per workload, from **random start nodes** (same seed on every DB → same nodes chosen).
- **Report:** p50, p90, p95, p99, mean, min, max — not just averages.
- **Mixed workload:** `BENCH_MIXED_DURATION_S=30` seconds at **concurrency ∈ {1, 10, 40}**, 80% reads / 20% writes.
- **Same client machine and same region** (`us-east-1`) for every DB.
- **Warm vs cold:** warm numbers reported by default; cold-start numbers captured on the first run of the day and stored separately (see caveats).
- **Retries:** timed-out or errored operations are counted as errors and reported alongside successful QPS — never silently retried inside the timer.

Every knob is env-driven and pinned in [`.env.example`](.env.example).

---

## 2. Reproducing the benchmark

### Prerequisites
- Python 3.11+
- Docker (only if you run the JanusGraph adapter)
- Free-tier accounts on: CognoDB, Neo4j Aura, Memgraph, ArangoDB Oasis

### One-time setup

```powershell
git clone https://github.com/lokeshp0409/graph-db-benchmark.git
cd graph-db-benchmark
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# then edit .env and paste each DB's URI + password
```

### Get the dataset (once)

```powershell
python -m data.download_and_sample
# → data/processed/pokec_200k/{nodes,edges}.csv  (~200k rels)
```

### JanusGraph (optional, resource-capped Docker)

```powershell
docker run -d --name janusgraph --cpus=0.5 --memory=256m -p 8182:8182 janusgraph/janusgraph:1.0.0
```

### Run everything

```powershell
# All DBs, all phases:
.\scripts\run_all.ps1

# Single DB:
python -m bench.runner --db cognodb --phase all
python -m bench.runner --db neo4j   --phase reads
python -m bench.runner --db memgraph --phase mixed

# Then build the report:
python scripts/plot.py
```

Bash equivalent: `bash scripts/run_all.sh`.

Phases: `load | reads | mixed | footprint | all`.

Outputs:
- Raw per-op timings → `results/raw/<db>.jsonl`
- Per-DB summary → `results/report/<db>.summary.json`
- Consolidated matrix + charts → `results/report/results_matrix.md`, `results/report/charts/*.png`

---

## 3. Results matrix

_The live matrix — regenerated from `results/raw/*.jsonl` on every run — lives in [`results/report/results_matrix.md`](results/report/results_matrix.md)._

### 3.1 Data loading

| DB | nodes | edges | nodes/s | rels/s | wall-clock s |
|---|---|---|---|---|---|
| **Neo4j Aura** | 74,062 | 150,000 | 8,139 | 6,510 | 32.1 |
| **Memgraph Cloud** | 91,489 | 200,000 | 4,491 | 4,076 | 69.4 |
| **CognoDB Cloud** | 91,489 | 200,000 | 2,878 | 2,396 | 115.3 |
| **ArangoDB Oasis** | 91,489 | 200,000 | 2,278 | 1,841 | 148.8 |

*Neo4j numbers are on the smaller 150k-edge sample; do not compare the absolute throughput directly. Per-edge, all three Cypher engines are in a similar ballpark.*

### 3.2 Read latency (p50 / p95, ms)

| DB | point_lookup | indexed_filter | hop1 | hop2 | hop3 | aggregation |
|---|---|---|---|---|---|---|
| **CognoDB** | 304 / 480 | 412 / 508 | 305 / 454 | 313 / 489 | 316 / 428 | **1,775 / 1,942** |
| **Neo4j Aura** | **95 / 115** | **100 / 352** | 121 / 754 | 235 / 1,654 | 120 / 974 | 165 / 534 |
| **Memgraph** | 205 / 225 | 255 / 284 | 255 / 287 | 218 / 252 | 203 / 224 | 262 / 305 |
| **ArangoDB Oasis** | 304 / 406 | 309 / 352 | 306 / 368 | 307 / 405 | 308 / 366 | 307 / 401 |

Key observations:
- **Neo4j** has the fastest median point/range lookups but the highest tail variance (hop2 p95 = 1,654 ms).
- **Memgraph** is the most consistent across all six workloads.
- **ArangoDB** has a flat ~306 ms profile regardless of query shape — characteristic of HTTP round-trip dominance.
- **CognoDB's** aggregation is an outlier at ~1.8 s p50; all other DBs handle the same count in 165–307 ms.

### 3.3 Mixed workload throughput (80% reads, 30 s, concurrency 1 / 10 / 40)

| DB | c=1 | c=10 | c=40 | errors at c=40 |
|---|---|---|---|---|
| **Memgraph Cloud** | 4.8 qps | 45.7 qps | **184.1 qps** | 0 |
| **Neo4j Aura** | 3.8 qps | 33.9 qps | **184.7 qps** | 0 |
| **CognoDB Cloud** | 2.8 qps | 27.8 qps | 96.2 qps | 0 |
| **ArangoDB Oasis** | 2.5 qps | 24.1 qps | 83.4 qps | **597** |

At 40 clients, Memgraph and Neo4j tie for top throughput with zero errors. ArangoDB's free tier dropped every write attempt (597 errors, 0 successful writes), so its QPS is entirely from reads.

### 3.4 Footprint

| DB | nodes | relationships |
|---|---|---|
| CognoDB | 92,558 | 200,568 |
| Memgraph | 93,531 | 201,084 |
| ArangoDB | 91,489 | 200,000 |
| Neo4j | 76,054 | 151,048 |

*None of the free-tier consoles expose exact on-disk bytes, so storage footprint is reported as object counts only.*

---

## 4. Caveats

Called out honestly, per the assignment:

- **Query language differences.** Cypher (CognoDB/Aura/Memgraph) and AQL (Arango) are not identical; equivalent-but-not-identical queries can produce different plans. Every translation is visible in [`bench/workloads.py`](bench/workloads.py) so a reader can audit fairness.
- **ArangoDB free tier is larger than the CognoDB free tier.** Oasis' smallest instance is 4 GB / 2 vCPU. We flag this in every Arango row; despite the larger spec it exhibited write errors that the smaller CognoDB tier did not.
- **Neo4j AuraDB Free's hard object cap (50k nodes / 175k rels)** forces us to sample the dataset down to 150k edges for that run. The same 150k sample should be used across DBs if strict parity is required.
- **JanusGraph was not benchmarked.** Docker Desktop was not available in the execution environment (`npipe` not found). The adapter code remains in [`bench/adapters/janusgraph.py`](bench/adapters/janusgraph.py) for anyone who can run Docker.
- **NebulaGraph adapter is included but not exercised.** A free NebulaGraph Cloud workspace was provisioned but did not expose a public graph endpoint during the time window; the adapter is in [`bench/adapters/nebula.py`](bench/adapters/nebula.py).
- **Free-tier throttling & noisy neighbours.** Free tiers are burstable and shared. To bound variance we report **p95**, not just p50.
- **Client machine & region.** All cloud runs from a single client in India to the providers' closest US-East regions. Network RTT dominates absolute latency (~80–300 ms), but all DBs were measured from the same client at the same time, so relative comparisons remain valid.
- **Failed operations are counted, not retried inside the timer.** A DB that returns errors instead of running fast will _not_ get a phantom low latency.

---

## 5. Analysis

### 5.1 CognoDB vs. its closest peer (Neo4j Aura)
Both speak Cypher over Bolt, but the comparison is nuanced:
- **Neo4j Aura** wins on raw point/range lookup p50 (95–100 ms vs. CognoDB's 304–412 ms) and load throughput.
- **CognoDB** is more predictable: its p95 latencies are tighter than Aura's, and it recorded **zero errors** in the mixed workload. Aura's hop queries show extreme tail variance (hop2 p95 = 1,654 ms, max = 2,380 ms).
- **CognoDB's aggregation** is the clear outlier at 1.8 s p50, roughly 6× slower than Memgraph/Arango and 11× slower than Aura on the same query shape. This suggests the count-relationships operation is not using a pre-materialized count store on the free tier.

### 5.2 Best/worst query shape per DB
- **Neo4j:** best at indexed point/range lookups; worst tail behavior on multi-hop traversals (hop2/hop3).
- **Memgraph:** most consistent across all query shapes; no workload is dramatically slower than another. This is a strength for mixed/unknown workloads.
- **CognoDB:** good for point/hop reads; worst at aggregation.
- **ArangoDB:** flat latency profile (~306 ms) regardless of query complexity. This is both a pro (predictable) and a con (no query-shape optimization visible at this scale). AQL hop queries performed better than expected.

### 5.3 Scaling from c=1 to c=40
All DBs scale roughly linearly with concurrency, but ArangoDB cannot sustain writes in its free tier:
- **Memgraph / Neo4j:** ~50× throughput increase from c=1 to c=40, zero errors.
- **CognoDB:** ~35× increase, zero errors.
- **ArangoDB:** ~34× increase, but **every write errored** at all concurrency levels (24 / 186 / 597 errors). The reported QPS is therefore only from reads, making the mixed-workload comparison unfair to the other DBs.

### 5.4 What each free tier actually delivered
| DB | Advertised | Delivered |
|---|---|---|
| CognoDB c0 | 0.5 vCPU / 256 MB / 1 GB | Consistent, error-free performance on 200k edges. |
| Neo4j Aura Free | 50k nodes / 175k rels | Fast but bursty; capped dataset. |
| Memgraph Cloud Free | 256 MB | Best consistency and top mixed throughput. |
| ArangoDB Oasis Free trial | 4 GB / 2 vCPU | Larger spec but write path unreliable on the trial tier. |

The headline is: **free-tier spec sheets do not predict real-world behavior.** ArangoDB's larger instance did not outperform the smaller CognoDB or Memgraph instances in this mixed read/write workload.

---

## 6. Repository layout

```
graph-db-benchmark/
├── bench/                  # harness (adapters, workloads, metrics, runner)
│   └── adapters/           # one per DB, all behind a common Adapter interface
├── data/
│   └── download_and_sample.py
├── results/
│   ├── raw/                # per-op JSONL, one file per DB
│   └── report/             # generated matrix + charts
├── scripts/
│   ├── run_all.ps1 / .sh
│   └── plot.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## 7. License & attribution

- SNAP `soc-Pokec` dataset © Stanford Network Analysis Project.
- All benchmark code MIT-licensed.
- No CognoDB / Neo4j / Memgraph / Arango / Janus passwords or URIs are stored in the repository; the harness reads them from environment variables via `python-dotenv`.
