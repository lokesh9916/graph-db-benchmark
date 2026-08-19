"""Logical workload definitions.

Each adapter translates these into its native query language. Keeping them
here makes the "same logical query on every DB" requirement auditable.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---- Cypher (CognoDB, Neo4j Aura, Memgraph) -----------------------------------
CYPHER = {
    "point_lookup":
        "MATCH (u:User {id: $id}) RETURN u.id AS id",
    "indexed_filter":
        "MATCH (u:User) WHERE u.id >= $lo AND u.id < $hi RETURN count(u) AS c",
    "hop1":
        "MATCH (u:User {id: $id})-[:FOLLOWS]->(v) RETURN count(v) AS c",
    "hop2":
        "MATCH (u:User {id: $id})-[:FOLLOWS*2..2]->(v) RETURN count(DISTINCT v) AS c",
    "hop3":
        "MATCH (u:User {id: $id})-[:FOLLOWS*3..3]->(v) RETURN count(DISTINCT v) AS c",
    "aggregation":
        "MATCH (:User)-[r:FOLLOWS]->(:User) RETURN count(r) AS c",
    "write":
        "MERGE (a:User {id: $a}) MERGE (b:User {id: $b}) MERGE (a)-[:FOLLOWS]->(b)",
}

# ---- AQL (ArangoDB) -----------------------------------------------------------
AQL = {
    "point_lookup":
        "FOR u IN users FILTER u._key == @id LIMIT 1 RETURN u._key",
    "indexed_filter":
        "RETURN LENGTH(FOR u IN users FILTER u.id >= @lo AND u.id < @hi RETURN 1)",
    "hop1":
        "RETURN LENGTH(FOR v IN 1..1 OUTBOUND CONCAT('users/', @id) follows RETURN 1)",
    "hop2":
        "RETURN LENGTH(FOR v IN 2..2 OUTBOUND CONCAT('users/', @id) follows OPTIONS {uniqueVertices:'global', bfs:true} RETURN 1)",
    "hop3":
        "RETURN LENGTH(FOR v IN 3..3 OUTBOUND CONCAT('users/', @id) follows OPTIONS {uniqueVertices:'global', bfs:true} RETURN 1)",
    "aggregation":
        "RETURN LENGTH(follows)",
    "write":
        "UPSERT {_key:@a} INSERT {_key:@a,id:@a} UPDATE {} IN users "
        "LET _ = (UPSERT {_key:@b} INSERT {_key:@b,id:@b} UPDATE {} IN users) "
        "INSERT {_from: CONCAT('users/',@a), _to: CONCAT('users/',@b)} INTO follows",
}

# ---- Gremlin (JanusGraph) -----------------------------------------------------
GREMLIN = {
    "point_lookup":
        "g.V().has('User','id', id).id()",
    "indexed_filter":
        "g.V().hasLabel('User').has('id', between(lo, hi)).count()",
    "hop1":
        "g.V().has('User','id', id).out('FOLLOWS').count()",
    "hop2":
        "g.V().has('User','id', id).out('FOLLOWS').out('FOLLOWS').dedup().count()",
    "hop3":
        "g.V().has('User','id', id).out('FOLLOWS').out('FOLLOWS').out('FOLLOWS').dedup().count()",
    "aggregation":
        "g.E().hasLabel('FOLLOWS').count()",
    "write":
        "g.V().has('User','id', a).fold().coalesce(unfold(), addV('User').property('id', a)).as('A')."
        "V().has('User','id', b).fold().coalesce(unfold(), addV('User').property('id', b)).as('B')."
        "addE('FOLLOWS').from('A').to('B')",
}


@dataclass(frozen=True)
class WorkloadName:
    POINT = "point_lookup"
    INDEXED = "indexed_filter"
    HOP1 = "hop1"
    HOP2 = "hop2"
    HOP3 = "hop3"
    AGG = "aggregation"
    WRITE = "write"


READ_WORKLOADS = [WorkloadName.POINT, WorkloadName.INDEXED,
                  WorkloadName.HOP1, WorkloadName.HOP2, WorkloadName.HOP3,
                  WorkloadName.AGG]
