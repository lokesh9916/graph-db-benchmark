"""Shared implementation for any Bolt/Cypher backend (Cogno, Aura, Memgraph)."""
from __future__ import annotations

from typing import Any, Iterable

from neo4j import GraphDatabase

from ..workloads import CYPHER
from .base import Adapter


class CypherAdapter(Adapter):
    uri: str = ""
    user: str = ""
    password: str = ""
    database: str | None = None

    def connect(self) -> None:
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        # Aura Free sometimes fails routing verification during provisioning;
        # queries themselves may still work. Don't abort the benchmark for this.
        try:
            self._driver.verify_connectivity()
        except Exception as e:
            print(f"[warn] verify_connectivity failed: {e}; continuing anyway")

    def close(self) -> None:
        self._driver.close()

    def _session(self):
        return self._driver.session(database=self.database) if self.database else self._driver.session()

    def reset_schema(self) -> None:
        with self._session() as s:
            s.run("MATCH (n) DETACH DELETE n").consume()
            s.run("CREATE INDEX user_id IF NOT EXISTS FOR (u:User) ON (u.id)").consume()

    def load_nodes(self, ids: Iterable[int], batch_size: int = 1000) -> int:
        import time
        t0 = time.perf_counter()
        batch: list[int] = []
        total = 0
        with self._session() as s:
            for i in ids:
                batch.append(int(i))
                if len(batch) >= batch_size:
                    s.run("UNWIND $ids AS id MERGE (:User {id: id})", ids=batch).consume()
                    total += len(batch)
                    batch = []
            if batch:
                s.run("UNWIND $ids AS id MERGE (:User {id: id})", ids=batch).consume()
                total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def load_edges(self, edges: Iterable[tuple[int, int]], batch_size: int = 1000) -> int:
        import time
        t0 = time.perf_counter()
        batch: list[dict] = []
        total = 0
        query = (
            "UNWIND $rows AS r "
            "MATCH (a:User {id: r.a}), (b:User {id: r.b}) "
            "MERGE (a)-[:FOLLOWS]->(b)"
        )
        with self._session() as s:
            for a, b in edges:
                batch.append({"a": int(a), "b": int(b)})
                if len(batch) >= batch_size:
                    s.run(query, rows=batch).consume()
                    total += len(batch)
                    batch = []
            if batch:
                s.run(query, rows=batch).consume()
                total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def run_read(self, workload: str, params: dict[str, Any]) -> Any:
        q = CYPHER[workload]
        with self._session() as s:
            return list(s.run(q, **params))

    def run_write(self, params: dict[str, Any]) -> Any:
        with self._session() as s:
            return s.run(CYPHER["write"], **params).consume()

    def observable_footprint(self) -> dict[str, Any]:
        with self._session() as s:
            nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        return {"nodes": nodes, "relationships": rels, "storage_bytes": "not observable"}
