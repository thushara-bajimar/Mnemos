"""The Mnemos engine: one object wiring settings, database, stores and services.

The FastAPI app holds one engine; tests and the evaluation lab create
isolated engines on temporary directories.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict

from .config import TUNABLE_KEYS, Settings
from .core.embeddings import make_embedder
from .db import Database
from .stores.stores import FileStore, GraphStore, KeywordStore, StructuredStore, VectorStore

log = logging.getLogger("mnemos")


class Mnemos:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.ensure_dirs()
        self.db = Database(self.settings.db_path)
        self._load_overrides()
        self.embedder = make_embedder(self.settings.embedding_dim)
        self.structured = StructuredStore(self.db)
        self.keyword = KeywordStore(self.db)
        self.vector = VectorStore(self.db, self.embedder)
        self.graph = GraphStore(self.db)
        self.files = FileStore(self.settings.files_dir)
        self._cache: OrderedDict = OrderedDict()
        self._cache_lock = threading.RLock()

        from .services.agents import AgentService
        from .services.forgetting import ForgettingService
        from .services.memory import MemoryService
        from .services.retrieval import Retriever

        self.forgetting = ForgettingService(self)
        self.memory = MemoryService(self)
        self.retriever = Retriever(self)
        self.agents = AgentService(self)
        log.info("Mnemos engine ready (db=%s, vectors=%d)", self.settings.db_path, self.vector.size())

    # ------------------------------------------------------- settings
    def _load_overrides(self) -> None:
        for r in self.db.query("SELECT key, value FROM kv_settings WHERE key LIKE 'cfg:%'"):
            k = r["key"][4:]
            if k in TUNABLE_KEYS:
                setattr(self.settings, k, json.loads(r["value"]))

    def update_settings(self, values: dict) -> dict:
        for k, v in values.items():
            if k not in TUNABLE_KEYS:
                raise ValueError(f"setting '{k}' is not tunable")
            typ = TUNABLE_KEYS[k]
            v = typ(v)
            if typ is float and not (0.0 <= v <= 1.0) and k != "default_temporary_hours":
                raise ValueError(f"{k} must be between 0 and 1")
            if k == "default_token_budget" and not (50 <= v <= 20000):
                raise ValueError("default_token_budget must be between 50 and 20000")
            setattr(self.settings, k, v)
            self.db.execute("INSERT OR REPLACE INTO kv_settings (key, value) VALUES (?,?)", (f"cfg:{k}", json.dumps(v)))
        self.invalidate_cache()
        return self.settings.public_dict()

    # ------------------------------------------------------- cache
    def cache_get(self, key):
        with self._cache_lock:
            v = self._cache.get(key)
            if v is not None:
                self._cache.move_to_end(key)
            return v

    def cache_put(self, key, value) -> None:
        with self._cache_lock:
            self._cache[key] = value
            while len(self._cache) > 256:
                self._cache.popitem(last=False)

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def cache_contains(self, memory_id: str) -> bool:
        with self._cache_lock:
            return any(memory_id in json.dumps(v, default=str) for v in self._cache.values())

    # ------------------------------------------------------- stats
    def stats(self) -> dict:
        q = self.db.query
        by_status = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM memories GROUP BY status")}
        by_type = {r["memory_type"]: r["n"] for r in q("SELECT memory_type, COUNT(*) n FROM memories WHERE status='active' GROUP BY memory_type")}
        by_action = {r["action"]: r["n"] for r in q("SELECT action, COUNT(*) n FROM decisions GROUP BY action")}
        by_source = {r["source_type"] or "?": r["n"] for r in q("SELECT source_type, COUNT(*) n FROM memories GROUP BY source_type")}
        routes: dict[str, int] = {}
        for r in q("SELECT storage_routes FROM memories"):
            for x in json.loads(r["storage_routes"]):
                routes[x] = routes.get(x, 0) + 1
        one = self.db.one
        import os

        db_bytes = sum(os.path.getsize(p) for p in [self.settings.db_path, str(self.settings.db_path) + "-wal"] if os.path.exists(p))
        from .core.tokenizer import info

        return {
            "total_memories": sum(by_status.values()),
            "by_status": by_status, "by_type": by_type, "by_decision": by_action, "by_source": by_source,
            "by_route": routes,
            "open_conflicts": one("SELECT COUNT(*) n FROM conflicts WHERE status='open'")["n"],
            "pending_confirmations": by_status.get("pending_confirmation", 0) + by_status.get("quarantined", 0),
            "deletions": one("SELECT COALESCE(SUM(deleted_count),0) n FROM deletion_audit WHERE scope!='expiry'")["n"],
            "expired": one("SELECT COALESCE(SUM(deleted_count),0) n FROM deletion_audit WHERE scope='expiry'")["n"],
            "entities": one("SELECT COUNT(*) n FROM entities")["n"],
            "edges": one("SELECT COUNT(*) n FROM edges")["n"],
            "vectors": self.vector.size(),
            "files": len(list(self.settings.files_dir.glob("*.md"))),
            "handovers": one("SELECT COUNT(*) n FROM handovers")["n"],
            "tasks": one("SELECT COUNT(*) n FROM tasks")["n"],
            "eval_runs": one("SELECT COUNT(*) n FROM eval_runs")["n"],
            "db_bytes": db_bytes, "file_bytes": self.files.disk_bytes(),
            "tokenizer": info(), "embedder": self.embedder.name,
        }

    def close(self) -> None:
        self.db.close()
