"""Build the results matrix + charts from results/raw/*.jsonl."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

RAW_DIR = Path("results/raw")
REPORT_DIR = Path("results/report")
CHARTS = REPORT_DIR / "charts"


def load_records() -> pd.DataFrame:
    rows = []
    for f in RAW_DIR.glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def markdown_table(df: pd.DataFrame, cols: list[str]) -> str:
    df = df[cols]
    header = "| " + " | ".join(cols) + " |\n"
    sep = "|" + "|".join(["---"] * len(cols)) + "|\n"
    body = ""
    for _, r in df.iterrows():
        body += "| " + " | ".join(
            f"{v:.2f}" if isinstance(v, float) else str(v) for v in r
        ) + " |\n"
    return header + sep + body


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    df = load_records()
    if df.empty:
        print("No results found under results/raw/. Run the harness first.")
        return

    out = ["# Results matrix\n"]

    # ---- Load throughput -----------------------------------------------------
    loads = df[df["phase"] == "load"].copy()
    if not loads.empty:
        out.append("## Data loading\n")
        out.append(markdown_table(
            loads.sort_values("db"),
            ["db", "nodes", "edges", "nodes_per_sec", "rels_per_sec", "load_wallclock_s"],
        ))

    # ---- Read latency --------------------------------------------------------
    reads = df[df["phase"] == "reads"].copy()
    if not reads.empty:
        out.append("\n## Read latency (ms)\n")
        out.append(markdown_table(
            reads.sort_values(["workload", "db"]),
            ["db", "workload", "n", "p50_ms", "p95_ms", "p99_ms", "mean_ms"],
        ))

        # p50 comparison chart per workload
        for w, sub in reads.groupby("workload"):
            fig, ax = plt.subplots(figsize=(6, 3.5))
            sub_sorted = sub.sort_values("db")
            ax.bar(sub_sorted["db"], sub_sorted["p50_ms"])
            ax.set_title(f"{w} p50 latency (ms)")
            ax.set_ylabel("ms")
            plt.xticks(rotation=20)
            fig.tight_layout()
            fig.savefig(CHARTS / f"reads_{w}_p50.png", dpi=140)
            plt.close(fig)

    # ---- Mixed workload ------------------------------------------------------
    mixed = df[df["phase"] == "mixed"].copy()
    if not mixed.empty:
        out.append("\n## Mixed workload throughput\n")
        out.append(markdown_table(
            mixed.sort_values(["concurrency", "db"]),
            ["db", "concurrency", "read_pct", "throughput_qps", "p50_ms", "p95_ms", "errors"],
        ))

        for c, sub in mixed.groupby("concurrency"):
            fig, ax = plt.subplots(figsize=(6, 3.5))
            sub_sorted = sub.sort_values("db")
            ax.bar(sub_sorted["db"], sub_sorted["throughput_qps"])
            ax.set_title(f"Mixed workload QPS (c={c})")
            ax.set_ylabel("qps")
            plt.xticks(rotation=20)
            fig.tight_layout()
            fig.savefig(CHARTS / f"mixed_c{c}_qps.png", dpi=140)
            plt.close(fig)

    # ---- Footprint -----------------------------------------------------------
    fp = df[df["phase"] == "footprint"].copy()
    if not fp.empty:
        out.append("\n## Footprint\n")
        out.append(markdown_table(
            fp.sort_values("db"),
            ["db", "nodes", "relationships", "storage_bytes"],
        ))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "results_matrix.md").write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {REPORT_DIR/'results_matrix.md'} and charts under {CHARTS}")


if __name__ == "__main__":
    main()
