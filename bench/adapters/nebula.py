"""NebulaGraph adapter using nebula3-python.

NebulaGraph uses nGQL, not Cypher/Gremlin/AQL. The queries here are semantically
equivalent to the shared workloads in bench.workloads.
"""
from __future__ import annotations

import time
from typing import Any, Iterable

from nebula3.Config import Config
from nebula3.data.ResultSet import ResultSet
from nebula3.gclient.net.ConnectionPool import ConnectionPool

from ..config import nebula_env
from .base import Adapter

NEBULA_QUERIES = {
    "point_lookup": "LOOKUP ON User WHERE User.id == $id YIELD properties(vertex).id AS id;",
    "indexed_filter": "LOOKUP ON User WHERE User.id >= $lo AND User.id < $hi YIELD properties(vertex).id AS id | YIELD COUNT(*) AS c;",
    "hop1": "GO 1 STEPS FROM $id OVER FOLLOWS YIELD COUNT(DISTINCT dst(edge)) AS c;",
    "hop2": "GO 2 STEPS FROM $id OVER FOLLOWS YIELD COUNT(DISTINCT dst(edge)) AS c;",
    "hop3": "GO 3 STEPS FROM $id OVER FOLLOWS YIELD COUNT(DISTINCT dst(edge)) AS c;",
    "aggregation": "MATCH ()-[e:FOLLOWS]->() RETURN COUNT(e) AS c;",
    "write": (
        "INSERT VERTEX IF NOT EXISTS User(id) VALUES $a:($a), $b:($b); "
        "INSERT EDGE IF NOT EXISTS FOLLOWS() VALUES $a->$b:();"
    ),
}


def _result_to_list(rs: ResultSet) -> list[dict]:
    if not rs.is_succeeded():
        raise RuntimeError(rs.error_msg())
    rows = []
    for row in rs.rows():
        d: dict = {}
        for col, val in zip(rs.keys(), row.values):
            d[col] = _unwrap(val)
        rows.append(d)
    return rows


def _unwrap(val):
    # Simplified unwrapping for common Nebula Value types.
    if val.is_int():
        return val.as_int()
    if val.is_str():
        return val.as_str()
    if val.is_bool():
        return val.as_bool()
    if val.is_double():
        return val.as_double()
    return str(val)


class NebulaAdapter(Adapter):
    name = "nebula"

    def __init__(self) -> None:
        self._env = nebula_env()
        self._space = self._env.get("space", "benchmark")

    def connect(self) -> None:
        config = Config()
        config.max_connection_pool_size = 10
        self._pool = ConnectionPool()
        ok = self._pool.init(
            [(self._env["host"], int(self._env["port"]))],
            config,
        )
        if not ok:
            raise RuntimeError("Failed to initialize NebulaGraph connection pool")
        self._session = self._pool.get_session(self._env["user"], self._env["password"])
        # Ensure the graph space exists.
        self._session.execute(f"CREATE SPACE IF NOT EXISTS {self._space}(vid_type=INT64);")
        time.sleep(1)  # give time for space creation to propagate
        self._session.execute(f"USE {self._space};")

    def close(self) -> None:
        try:
            self._session.release()
        except Exception:
            pass
        self._pool.close()

    def _exec(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        q = query
        if params:
            for k, v in params.items():
                q = q.replace(f"${k}", str(v))
        rs = self._session.execute(q)
        return _result_to_list(rs)

    def reset_schema(self) -> None:
        self._exec(f"USE {self._space};")
        self._exec("DROP TAG INDEX IF EXISTS user_id_idx;")
        self._exec("CLEAR SPACE {self._space};")
        self._exec("CREATE TAG IF NOT EXISTS User(id int);")
        self._exec("CREATE EDGE IF NOT EXISTS FOLLOWS();")
        self._exec("CREATE TAG INDEX IF NOT EXISTS user_id_idx ON User(id);")

    def load_nodes(self, ids: Iterable[int], batch_size: int = 1000) -> int:
        t0 = time.perf_counter()
        batch: list[int] = []
        total = 0
        for i in ids:
            batch.append(int(i))
            if len(batch) >= batch_size:
                values = ", ".join(f"{x}:({x})" for x in batch)
                self._exec(f"INSERT VERTEX User(id) VALUES {values};")
                total += len(batch)
                batch = []
        if batch:
            values = ", ".join(f"{x}:({x})" for x in batch)
            self._exec(f"INSERT VERTEX User(id) VALUES {values};")
            total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def load_edges(self, edges: Iterable[tuple[int, int]], batch_size: int = 1000) -> int:
        t0 = time.perf_counter()
        batch: list[tuple[int, int]] = []
        total = 0
        for a, b in edges:
            batch.append((int(a), int(b)))
            if len(batch) >= batch_size:
                values = ", ".join(f"{a}->{b}:()" for a, b in batch)
                self._exec(f"INSERT EDGE FOLLOWS() VALUES {values};")
                total += len(batch)
                batch = []
        if batch:
            values = ", ".join(f"{a}->{b}:()" for a, b in batch)
            self._exec(f"INSERT EDGE FOLLOWS() VALUES {values};")
            total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def run_read(self, workload: str, params: dict[str, Any]) -> Any:
        return self._exec(NEBULA_QUERIES[workload], params)

    def run_write(self, params: dict[str, Any]) -> Any:
        return self._exec(NEBULA_QUERIES["write"], params)

    def observable_footprint(self) -> dict[str, Any]:
        try:
            stats = self._exec("SHOW STATS;")[0]
        except Exception:
            stats = {}
        return {"nodes": stats.get("vertices", "not observable"),
                "relationships": stats.get("edges", "not observable"),
                "storage_bytes": "not observable"}
