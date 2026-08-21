# Run the full benchmark against every configured DB.
# Requires .env populated. Fails fast if a DB is unreachable.

param(
    [string[]] $Dbs = @("cognodb", "neo4j", "memgraph", "arangodb", "janusgraph", "kuzu"),
    [string]   $Phase = "all"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "data/processed/pokec_200k/edges.csv")) {
    Write-Host "Dataset missing. Downloading and sampling SNAP soc-Pokec..."
    python -m data.download_and_sample
}

foreach ($db in $Dbs) {
    Write-Host "==== Running phase='$Phase' on $db ===="
    python -m bench.runner --db $db --phase $Phase
}

Write-Host "==== Building report ===="
python scripts/plot.py

