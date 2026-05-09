from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import aiosqlite

from shadowtrace.core.config import CONFIG, DB_FILE, ShadowTraceConfig


class SQLiteCache:
    def __init__(self, db_file=DB_FILE, config: ShadowTraceConfig = CONFIG) -> None:
        self.db_file = db_file
        self.config = config
        self._conn: aiosqlite.Connection | None = None

    async def get_connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_file)
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    async def init(self) -> None:
        conn = await self.get_connection()
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY,
            username TEXT,
            site TEXT,
            url TEXT,
            found INTEGER,
            confidence INTEGER,
            avatar_hash TEXT,
            metadata TEXT,
            last_check TIMESTAMP,
            UNIQUE(username, site)
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS avatar_hash (
            url TEXT PRIMARY KEY,
            hash TEXT,
            checked_at TIMESTAMP
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS timeline (
            username TEXT, site TEXT, timestamp TEXT, avatar_hash TEXT, bio TEXT,
            name TEXT, uniqid TEXT, PRIMARY KEY(username, site, timestamp)
        )
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS passive_cache (
            engine TEXT,
            query TEXT,
            username TEXT,
            snippets TEXT,
            score INTEGER,
            ts TIMESTAMP,
            PRIMARY KEY(engine, query, username)
        )
        """)
        await conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
        self._conn = None

    async def get_profile(self, username: str, site: str) -> dict[str, Any] | None:
        conn = await self.get_connection()
        async with conn.execute(
            "SELECT url, found, confidence, avatar_hash, metadata, last_check FROM profiles WHERE username=? AND site=?",
            (username, site),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        url, found, confidence, avatar_hash, metadata, last_check = row
        return {
            "site": site,
            "username": username,
            "url": url,
            "status": "FOUND" if found else "NOT FOUND",
            "confidence": confidence,
            "avatar_hash": avatar_hash,
            "metadata": json.loads(metadata or "{}"),
            "cached": True,
            "last_check": last_check,
        }

    async def set_profile(
        self,
        username: str,
        site: str,
        url: str,
        found: bool,
        confidence: int,
        avatar_hash: str | None,
        metadata: dict[str, Any],
    ) -> None:
        conn = await self.get_connection()
        now = datetime.now().isoformat()
        await conn.execute(
            """
            INSERT OR REPLACE INTO profiles
            (username, site, url, found, confidence, avatar_hash, metadata, last_check)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username, site, url, int(found), confidence, avatar_hash, json.dumps(metadata), now),
        )
        await conn.execute(
            """
            INSERT OR REPLACE INTO timeline
            (username, site, timestamp, avatar_hash, bio, name, uniqid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                site,
                now,
                avatar_hash,
                metadata.get("bio"),
                metadata.get("full_name") or metadata.get("name") or "",
                hashlib.sha1(f"{username}{site}".encode()).hexdigest(),
            ),
        )
        await conn.commit()

    async def get_passive(self, engine: str, query: str, username: str) -> dict[str, Any] | None:
        conn = await self.get_connection()
        async with conn.execute(
            "SELECT snippets, score, ts FROM passive_cache WHERE engine=? AND query=? AND username=?",
            (engine, query, username),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        snippets, score, ts = row
        cache_dt = datetime.fromisoformat(ts)
        if (datetime.now() - cache_dt).total_seconds() >= self.config.passive_ttl_hours * 3600:
            return None
        return {"snippets": json.loads(snippets), "score": score, "ts": ts}

    async def set_passive(self, engine: str, query: str, username: str, snippets: list[dict], score: int) -> None:
        conn = await self.get_connection()
        await conn.execute(
            """
            INSERT OR REPLACE INTO passive_cache (engine, query, username, snippets, score, ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (engine, query, username, json.dumps(snippets), score, datetime.now().isoformat()),
        )
        await conn.commit()


cache = SQLiteCache()
