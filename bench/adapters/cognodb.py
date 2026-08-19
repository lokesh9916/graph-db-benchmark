from __future__ import annotations

from ..config import cognodb_env
from ._cypher_base import CypherAdapter


class CognoDBAdapter(CypherAdapter):
    name = "cognodb"

    def __init__(self) -> None:
        env = cognodb_env()
        self.uri = env["uri"]
        self.user = env["user"]
        self.password = env["password"]
