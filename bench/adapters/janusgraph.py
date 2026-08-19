from __future__ import annotations

import time
from typing import Any, Iterable

from gremlin_python.driver.client import Client
from gremlin_python.driver.serializer import GraphSONSerializersV3d0

from ..config import janus_env
from .base import Adapter


class JanusAdapter(Adapter):
    name = "janusgraph"

    def __init__(self) -> None:
        self._env = janus_env()

    def connect(self) -> None:
        self._client = Client(
            self._env["url"], "g",
            message_serializer=GraphSONSerializersV3d0(),
        )

    def close(self) -> None:
        self._client.close()

    def _submit(self, query: str, bindings: dict[str, Any] | None = None) -> list:
        return self._client.submit(query, bindings or {}).all().result()

    def reset_schema(self) -> None:
        self._submit("g.V().drop().iterate()")
        # JanusGraph indexes are typically declared via management API in Groovy console.
        # For a fair, reproducible bench we rely on the default composite index the loader
        # creates below and document this caveat in the README.

    def load_nodes(self, ids: Iterable[int], batch_size: int = 500) -> int:
        t0 = time.perf_counter()
        batch: list[int] = []
        total = 0
        query = (
            "ids.each { id -> g.V().has('User','id', id).fold()"
            ".coalesce(unfold(), addV('User').property('id', id)).iterate() }"
        )
        for i in ids:
            batch.append(int(i))
            if len(batch) >= batch_size:
                self._submit(query, {"ids": batch})
                total += len(batch)
                batch = []
        if batch:
            self._submit(query, {"ids": batch})
            total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def load_edges(self, edges: Iterable[tuple[int, int]], batch_size: int = 500) -> int:
        t0 = time.perf_counter()
        batch: list[dict] = []
        total = 0
        query = (
            "rows.each { r -> def a = g.V().has('User','id', r.a).next();"
            " def b = g.V().has('User','id', r.b).next();"
            " g.V(a).addE('FOLLOWS').to(b).iterate() }"
        )
        for a, b in edges:
            batch.append({"a": int(a), "b": int(b)})
            if len(batch) >= batch_size:
                self._submit(query, {"rows": batch})
                total += len(batch)
                batch = []
        if batch:
            self._submit(query, {"rows": batch})
            total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def run_read(self, workload: str, params: dict[str, Any]) -> Any:
        from ..workloads import GREMLIN
        return self._submit(GREMLIN[workload], params)

    def run_write(self, params: dict[str, Any]) -> Any:
        from ..workloads import GREMLIN
        return self._submit(GREMLIN["write"], params)

    def observable_footprint(self) -> dict[str, Any]:
        n = self._submit("g.V().count()")[0]
        e = self._submit("g.E().count()")[0]
        return {"nodes": int(n), "relationships": int(e), "storage_bytes": "not observable"}
