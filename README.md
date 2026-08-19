# Graph Database Cloud Benchmark

**A reproducible, honest benchmark of [CognoDB Cloud](https://console.cognodb.com) against four other managed / self-hosted graph databases on the same dataset, the same logical queries, and the same resource envelope.**

> This repository is a submission for the Wexa AI take-home assignment.
> The goal is engineering rigor and honesty, **not** picking a "winner."

---

## TL;DR

| DB | Tier | Query language | Verdict (short) |
|---|---|---|---|
| **CognoDB Cloud** | free `c0` — 0.5 vCPU / 256 MB / 1 GB | Cypher (Bolt) | _to be filled after runs_ |
| **Neo4j AuraDB Free** | free — 50k nodes / 175k rels limit | Cypher (Bolt) | _to be filled_ |
| **Memgraph Cloud** | free — 256 MB | Cypher (Bolt) | _to be filled_ |
| **ArangoDB Oasis** | free trial — smallest instance | AQL (HTTP) | _to be filled_ |
| **JanusGraph** | self-hosted, Docker capped 0.5 CPU / 256 MB | Gremlin (WS) | _to be filled_ |

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
- **Sample:** first **200,000 directed edges** over **~120k unique nodes** (deterministic, seed=42).
- Sized to fit the smallest tier (Neo4j Aura Free has the tightest cap at 175k rels — if you run against Aura, set `--edges 150000`).

### 1.3 Same logical queries
Defined once in [`bench/workloads.py`](bench/workloads.py) and translated per DB:

| Workload | Cypher | AQL | Gremlin |
|---|---|---|---|
| Point lookup | `MATCH (u:User {id:$id})` | `FILTER u._key == @id` | `g.V().has('User','id',id)` |
| Indexed range | `WHERE u.id >= $lo AND u.id < $hi` | `FILTER u.id >= @lo AND u.id < @hi` | `has('id', between(lo,hi))` |
| 1/2/3-hop | `-[:FOLLOWS*k..k]->` | `k..k OUTBOUND … follows` | `.out('FOLLOWS')` chained |
| Aggregation | `MATCH ()-[r:FOLLOWS]->() RETURN count(r)` | `LENGTH(follows)` | `g.E().hasLabel('FOLLOWS').count()` |
| Write | `MERGE (a)-[:FOLLOWS]->(b)` | `UPSERT … INSERT … INTO follows` | `addV / addE` idempotent |

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

### 3.1 Data loading (nodes/s, rels/s, wall-clock s)
_will be filled in after runs_

### 3.2 Read latency, p50 / p95 (ms)
_will be filled in after runs — 6 workloads × 5 DBs_

### 3.3 Mixed workload QPS at concurrency ∈ {1, 10, 40}
_will be filled in after runs_

### 3.4 Footprint
_node count, relationship count, storage size where the platform exposes it_

---

## 4. Caveats

Called out honestly, per the assignment:

- **Query language differences.** Cypher (Cognō/Aura/Memgraph), AQL (Arango) and Gremlin (Janus) are not identical languages; equivalent-but-not-identical queries can produce different plans. Every translation is visible in [`bench/workloads.py`](bench/workloads.py) so a reader can audit fairness.
- **ArangoDB free tier is larger than the CognoDB free tier.** Oasis' smallest instance is 4 GB / 2 vCPU. We flag this in every Arango row of the results and, where relevant, discount Arango's absolute numbers when comparing.
- **Neo4j AuraDB Free's hard object cap (50k nodes / 175k rels)** forces us to sample the dataset down to 150k edges when running against Aura; the same sample is used across DBs during that run so the comparison stays fair.
- **JanusGraph indexes** for composite `User.id` are usually declared through the JanusGraph management API in Groovy; our loader relies on the default index, which is likely _slower_ for Janus than a real production setup. Called out explicitly.
- **Free-tier throttling & noisy neighbours.** Free tiers are burstable and shared. To bound variance we report **p95**, not just p50, and repeat the read phase 3× when possible; the variance across runs is included as a separate table in the report.
- **Cold-start numbers** are captured on the first run of the day and stored under `results/raw/*.cold.jsonl` — kept separate so they never contaminate steady-state numbers.
- **Client machine & region.** All runs from a single client in `us-east-1`. Network variance is not fully controllable; we report over multiple runs to bound it.
- **Failed operations are counted, not retried inside the timer.** A DB that returns errors instead of running fast will _not_ get a phantom low latency.

---

## 5. Analysis

_A short, honest write-up of what the numbers show and, where possible, why — populated once the runs are in._

Key questions the analysis will address:
1. Where does CognoDB sit against its closest peer (Aura)?
2. Which query shape is each DB best/worst at, and does the query plan explain it?
3. How does each DB scale from `c=1` to `c=40`? Which ones fall over on writes?
4. What does each free tier actually deliver vs. its advertised specs?

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
