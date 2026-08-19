from __future__ import annotations

from .base import Adapter


def get_adapter(name: str) -> Adapter:
    name = name.lower()
    if name == "cognodb":
        from .cognodb import CognoDBAdapter
        return CognoDBAdapter()
    if name == "neo4j":
        from .neo4j_aura import Neo4jAuraAdapter
        return Neo4jAuraAdapter()
    if name == "memgraph":
        from .memgraph import MemgraphAdapter
        return MemgraphAdapter()
    if name == "arangodb":
        from .arangodb import ArangoAdapter
        return ArangoAdapter()
    if name == "janusgraph":
        from .janusgraph import JanusAdapter
        return JanusAdapter()
    raise ValueError(f"Unknown adapter: {name}")


ALL_ADAPTERS = ["cognodb", "neo4j", "memgraph", "arangodb", "janusgraph"]
