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
    trust_all: bool = False

    def connect(self) -> None:
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        # Aura Free's routing endpoint sometimes lands on a cluster member that
        # doesn't host the user database. If the configured database exists on a
        # different member, reconnect directly to that member.
        try:
            self._driver.verify_connectivity()
        except Exception as e:
            print(f"[warn] verify_connectivity failed: {e}; continuing anyway")
        if self.database:
            self._reconnect_to_database_member()

    def _reconnect_to_database_member(self) -> None:
        from neo4j import GraphDatabase as _GraphDatabase
        try:
            # SHOW DATABASES is a system query; force system database.
            with self._driver.session(database="system") as s:
                rec = s.run(
                    "SHOW DATABASES YIELD name, address, currentStatus "
                    "WHERE name = $db AND currentStatus = 'online'",
                    db=self.database,
                ).single()
        except Exception as e:
            print(f"[warn] could not discover database member: {e}")
            return
        if not rec:
            print(f"[warn] database {self.database} not found or not online")
            return
        address = rec["address"]
        # Convert routing scheme to direct bolt scheme on the member address.
        scheme = "bolt+ssc" if self.uri.startswith(("bolt+s", "neo4j+s")) else "bolt"
        direct_uri = f"{scheme}://{address}"
        print(f"[neo4j] reconnecting directly to database member: {direct_uri}")
        try:
            new_driver = _GraphDatabase.driver(direct_uri, auth=(self.user, self.password))
            new_driver.verify_connectivity()
            self._driver.close()
            self._driver = new_driver
        except Exception as e:
            print(f"[warn] direct member connection failed: {e}; keeping original driver")

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
