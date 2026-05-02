from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import pymysql
from pymysql.connections import Connection


@dataclass
class DatabaseConfig:
    host: str
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = ""
    charset: str = "utf8mb4"

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": self.charset,
        }


@dataclass
class ConnectionInfo:
    config: DatabaseConfig
    schema_cache: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)


class DatabaseManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, ConnectionInfo] = {}

    def connect(self, user_id: str, config: DatabaseConfig) -> dict[str, Any]:
        conn = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            charset=config.charset,
            connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()

        with self._lock:
            self._connections[user_id] = ConnectionInfo(config=config)

        return {"status": "connected", "database": config.database, "host": config.host}

    def disconnect(self, user_id: str) -> bool:
        with self._lock:
            if user_id in self._connections:
                del self._connections[user_id]
                return True
            return False

    def get_connection_info(self, user_id: str) -> ConnectionInfo | None:
        with self._lock:
            return self._connections.get(user_id)

    def is_connected(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self._connections

    def get_raw_connection(self, user_id: str) -> Connection | None:
        info = self.get_connection_info(user_id)
        if not info:
            return None
        cfg = info.config
        return pymysql.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            charset=cfg.charset,
            connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def get_status(self, user_id: str) -> dict[str, Any]:
        info = self.get_connection_info(user_id)
        if not info:
            return {"connected": False}
        return {
            "connected": True,
            "host": info.config.host,
            "port": info.config.port,
            "database": info.config.database,
            "user": info.config.user,
            "tables_count": len(info.tables),
        }

    def set_schema_cache(self, user_id: str, schema_md: str, tables: list[dict[str, Any]]) -> None:
        with self._lock:
            info = self._connections.get(user_id)
            if info:
                info.schema_cache = schema_md
                info.tables = tables

    def get_schema_cache(self, user_id: str) -> str:
        with self._lock:
            info = self._connections.get(user_id)
            return info.schema_cache if info else ""


_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
