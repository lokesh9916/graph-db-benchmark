from __future__ import annotations

from typing import Any

from ..config import memgraph_env
from ._cypher_base import CypherAdapter


class MemgraphAdapter(CypherAdapter):
    name = "memgraph"

    def __init__(self) -> None:
        env = memgraph_env()
        self.uri = env["uri"]
        self.user = env["user"]
        self.password = env["password"]

    def reset_schema(self) -> None:
        # Memgraph uses slightly different index DDL.
        with self._session() as s:
            s.run("MATCH (n) DETACH DELETE n").consume()
            try:
                s.run("CREATE INDEX ON :User(id)").consume()
            except Exception:
                pass  # index may already exist
