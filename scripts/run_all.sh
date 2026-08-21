#!/usr/bin/env bash
# Run the full benchmark against every configured DB.
# Requires .env populated. Fails fast if a DB is unreachable.
set -euo pipefail

DBS=(${DBS:-cognodb neo4j memgraph arangodb janusgraph kuzu})
PHASE=${PHASE:-all}

if [[ ! -f data/processed/pokec_200k/edges.csv ]]; then
  echo "Dataset missing. Downloading and sampling SNAP soc-Pokec..."
  python -m data.download_and_sample
fi

for db in "${DBS[@]}"; do
  echo "==== Running phase='$PHASE' on $db ===="
  python -m bench.runner --db "$db" --phase "$PHASE"
done

echo "==== Building report ===="
python scripts/plot.py
