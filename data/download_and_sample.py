"""Download SNAP soc-Pokec-relationships, sample to ~200k edges, emit CSVs.

Output:
    data/processed/pokec_200k/nodes.csv   (id)
    data/processed/pokec_200k/edges.csv   (src,dst)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import random
import urllib.request
from pathlib import Path

SNAP_URL = "https://snap.stanford.edu/data/soc-pokec-relationships.txt.gz"


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    print(f"Downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)
    return dest


def sample_edges(gz_path: Path, target_edges: int, seed: int = 42) -> tuple[set[int], list[tuple[int, int]]]:
    """Take the first N edges from the SNAP file (already shuffled enough for a bench)."""
    edges: list[tuple[int, int]] = []
    nodes: set[int] = set()
    with gzip.open(gz_path, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            a_s, b_s = line.split()
            a, b = int(a_s), int(b_s)
            edges.append((a, b))
            nodes.add(a)
            nodes.add(b)
            if len(edges) >= target_edges:
                break
    return nodes, edges


def write_csvs(out_dir: Path, nodes: set[int], edges: list[tuple[int, int]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "nodes.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id"])
        for n in sorted(nodes):
            w.writerow([n])
    with (out_dir / "edges.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst"])
        for a, b in edges:
            w.writerow([a, b])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edges", type=int, default=200_000)
    ap.add_argument("--out", default="data/processed/pokec_200k")
    args = ap.parse_args()

    raw = Path("data/raw/soc-pokec-relationships.txt.gz")
    download(SNAP_URL, raw)

    print(f"Sampling first {args.edges:,} edges...")
    nodes, edges = sample_edges(raw, args.edges)
    print(f"Sampled {len(edges):,} edges over {len(nodes):,} nodes")

    out = Path(args.out)
    write_csvs(out, nodes, edges)
    print(f"Wrote {out/'nodes.csv'} and {out/'edges.csv'}")


if __name__ == "__main__":
    main()
