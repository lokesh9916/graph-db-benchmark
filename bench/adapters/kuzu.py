"""Kùzu adapter.

Kùzu is an embedded, in-process Cypher graph database. It is included as a
fifth comparison point, but because it runs locally with no network hop its
absolute latencies are not directly comparable to the managed cloud platforms.
This is documented as a caveat in the README.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Iterable

import kuzu

from ..config import CFG
from .base import Adapter

KUZU_QUERIES = {
    "point_lookup": "MATCH (u:User {id: $id}) RETURN u.id AS id",
    "indexed_filter": "MATCH (u:User) WHERE u.id >= $lo AND u.id < $hi RETURN count(u) AS c",
    "hop1": "MATCH (u:User {id: $id})-[:FOLLOWS]->(v) RETURN count(v) AS c",
    "hop2": "MATCH (u:User {id: $id})-[:FOLLOWS*2..2]->(v) RETURN count(DISTINCT v) AS c",
    "hop3": "MATCH (u:User {id: $id})-[:FOLLOWS*3..3]->(v) RETURN count(DISTINCT v) AS c",
    "aggregation": "MATCH (:User)-[r:FOLLOWS]->(:User) RETURN count(r) AS c",
    "write": "MERGE (a:User {id: $a}) MERGE (b:User {id: $b}) MERGE (a)-[:FOLLOWS]->(b)",
}


class KuzuAdapter(Adapter):
    name = "kuzu"

    def __init__(self) -> None:
        self._db_path = Path("data/processed/kuzu_db")

    def connect(self) -> None:
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)

    def close(self) -> None:
        # Connection and database are cleaned up by Python GC; explicitly delete
        # to release file locks before potential reset.
        import gc
        try:
            self._conn.close()
        except Exception:
            pass
        self._conn = None
        self._db = None
        gc.collect()

    def reset_schema(self) -> None:
        # Kùzu does not support dropping individual labels. Remove the whole
        # database path and recreate it.
        self.close()
        if self._db_path.exists():
            if self._db_path.is_dir():
                shutil.rmtree(self._db_path)
            else:
                self._db_path.unlink()
        self.connect()
        self._conn.execute("CREATE NODE TABLE User(id INT64, PRIMARY KEY(id))")
        self._conn.execute("CREATE REL TABLE FOLLOWS(FROM User TO User, MANY_MANY)")

    def load_nodes(self, ids: Iterable[int], batch_size: int = 1000) -> int:
        t0 = time.perf_counter()
        # Kùzu bulk COPY from CSV is the fastest path.
        nodes_path = CFG.dataset_dir / "nodes.csv"
        self._conn.execute(f'COPY User FROM "{nodes_path.as_posix()}" (header=true)')
        dt = max(time.perf_counter() - t0, 1e-9)
        # Count via file lines for total.
        total = sum(1 for _ in nodes_path.open()) - 1
        return int(total / dt)

    def load_edges(self, edges: Iterable[tuple[int, int]], batch_size: int = 1000) -> int:
        t0 = time.perf_counter()
        edges_path = CFG.dataset_dir / "edges.csv"
        self._conn.execute(f'COPY FOLLOWS FROM "{edges_path.as_posix()}" (header=true)')
        dt = max(time.perf_counter() - t0, 1e-9)
        total = sum(1 for _ in edges_path.open()) - 1
        return int(total / dt)

    def run_read(self, workload: str, params: dict[str, Any]) -> Any:
        q = KUZU_QUERIES[workload]
        result = self._conn.execute(q, params)
        # Drain first row to ensure timing includes full execution.
        row = result.get_next()
        return row[0] if row else None

    def run_write(self, params: dict[str, Any]) -> Any:
        q = KUZU_QUERIES["write"]
        result = self._conn.execute(q, params)
        return result.get_num_tuples()

    def observable_footprint(self) -> dict[str, Any]:
        nodes = self._conn.execute("MATCH (u:User) RETURN count(u) AS c").get_next()[0]
        rels = self._conn.execute("MATCH ()-[r:FOLLOWS]->() RETURN count(r) AS c").get_next()[0]
        if self._db_path.exists():
            if self._db_path.is_file():
                size = self._db_path.stat().st_size
            else:
                size = sum(f.stat().st_size for f in self._db_path.rglob("*") if f.is_file())
        else:
            size = 0
        return {"nodes": int(nodes), "relationships": int(rels), "storage_bytes": size}
