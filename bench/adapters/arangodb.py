from __future__ import annotations

import time
from typing import Any, Iterable

from arango import ArangoClient

from ..config import arango_env
from ..workloads import AQL
from .base import Adapter


class ArangoAdapter(Adapter):
    name = "arangodb"

    def __init__(self) -> None:
        self._env = arango_env()

    def connect(self) -> None:
        self._client = ArangoClient(hosts=self._env["url"])
        sys_db = self._client.db("_system", username=self._env["user"], password=self._env["password"])
        if not sys_db.has_database(self._env["db"]):
            sys_db.create_database(self._env["db"])
        self._db = self._client.db(self._env["db"], username=self._env["user"], password=self._env["password"])

    def close(self) -> None:
        pass  # HTTP client, nothing to close

    def reset_schema(self) -> None:
        for name in ("follows", "users"):
            if self._db.has_collection(name):
                self._db.delete_collection(name)
        users = self._db.create_collection("users")
        self._db.create_collection("follows", edge=True)
        users.add_index({"type": "persistent", "fields": ["id"]})

    def load_nodes(self, ids: Iterable[int], batch_size: int = 1000) -> int:
        t0 = time.perf_counter()
        users = self._db.collection("users")
        batch: list[dict] = []
        total = 0
        for i in ids:
            batch.append({"_key": str(i), "id": int(i)})
            if len(batch) >= batch_size:
                users.insert_many(batch, overwrite=True)
                total += len(batch)
                batch = []
        if batch:
            users.insert_many(batch, overwrite=True)
            total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def load_edges(self, edges: Iterable[tuple[int, int]], batch_size: int = 1000) -> int:
        t0 = time.perf_counter()
        follows = self._db.collection("follows")
        batch: list[dict] = []
        total = 0
        for a, b in edges:
            batch.append({"_from": f"users/{a}", "_to": f"users/{b}"})
            if len(batch) >= batch_size:
                follows.insert_many(batch)
                total += len(batch)
                batch = []
        if batch:
            follows.insert_many(batch)
            total += len(batch)
        dt = max(time.perf_counter() - t0, 1e-9)
        return int(total / dt)

    def run_read(self, workload: str, params: dict[str, Any]) -> Any:
        q = AQL[workload]
        bind = {}
        if "id" in params:
            bind["id"] = str(params["id"])
        if "lo" in params:
            bind["lo"] = int(params["lo"])
        if "hi" in params:
            bind["hi"] = int(params["hi"])
        cur = self._db.aql.execute(q, bind_vars=bind)
        return list(cur)

    def run_write(self, params: dict[str, Any]) -> Any:
        cur = self._db.aql.execute(AQL["write"], bind_vars={"a": str(params["a"]), "b": str(params["b"])})
        return list(cur)

    def observable_footprint(self) -> dict[str, Any]:
        users = self._db.collection("users").count()
        rels = self._db.collection("follows").count()
        return {"nodes": users, "relationships": rels, "storage_bytes": "not observable"}
