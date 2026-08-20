from __future__ import annotations

from ..config import neo4j_env
from ._cypher_base import CypherAdapter


class Neo4jAuraAdapter(CypherAdapter):
    name = "neo4j"

    def __init__(self) -> None:
        env = neo4j_env()
        self.uri = env["uri"]
        self.user = env["user"]
        self.password = env["password"]
        self.database = env.get("database")
        self.trust_all = env.get("trust_all", False)
