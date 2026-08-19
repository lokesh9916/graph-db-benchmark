from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable


class Adapter(ABC):
    name: str = "base"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def reset_schema(self) -> None:
        """Drop existing data + (re)create indexes/labels required by the workloads."""

    @abstractmethod
    def load_nodes(self, ids: Iterable[int], batch_size: int = 1000) -> int:
        """Bulk-load User nodes. Returns nodes/sec."""

    @abstractmethod
    def load_edges(self, edges: Iterable[tuple[int, int]], batch_size: int = 1000) -> int:
        """Bulk-load FOLLOWS edges. Returns rels/sec."""

    @abstractmethod
    def run_read(self, workload: str, params: dict[str, Any]) -> Any: ...

    @abstractmethod
    def run_write(self, params: dict[str, Any]) -> Any: ...

    @abstractmethod
    def observable_footprint(self) -> dict[str, Any]:
        """Return whatever the platform exposes (node count, rel count, db size)."""

    def __enter__(self) -> "Adapter":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
