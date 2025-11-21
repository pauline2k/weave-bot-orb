"""Database models and operations for the Discord bot."""
import sqlite3
import asyncio
from typing import Optional, List
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum


class ParseStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ParseRequest:
    id: Optional[int]
    discord_message_id: int
    discord_response_id: int
    agent_request_id: Optional[str]
    status: ParseStatus
    result_url: Optional[str]
    created_at: str
    updated_at: str


class Database:
    def __init__(self, db_path: str = "weave_bot.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parse_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_message_id INTEGER NOT NULL UNIQUE,
                    discord_response_id INTEGER NOT NULL,
                    agent_request_id TEXT,
                    status TEXT NOT NULL,
                    result_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for quick lookups by agent_request_id
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_request_id
                ON parse_requests(agent_request_id)
            """)

            conn.commit()
        finally:
            conn.close()

    async def create_request(
        self,
        discord_message_id: int,
        discord_response_id: int
    ) -> int:
        """Create a new parse request."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO parse_requests
                (discord_message_id, discord_response_id, status)
                VALUES (?, ?, ?)
                """,
                (discord_message_id, discord_response_id, ParseStatus.PENDING.value)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    async def update_agent_id(
        self,
        discord_message_id: int,
        agent_request_id: str
    ) -> bool:
        """Update the agent request ID for a parse request."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE parse_requests
                SET agent_request_id = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE discord_message_id = ?
                """,
                (agent_request_id, ParseStatus.IN_PROGRESS.value, discord_message_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    async def update_status(
        self,
        agent_request_id: str,
        status: ParseStatus,
        result_url: Optional[str] = None
    ) -> Optional[ParseRequest]:
        """Update the status of a parse request by agent ID."""
        conn = self._get_connection()
        try:
            if result_url:
                cursor = conn.execute(
                    """
                    UPDATE parse_requests
                    SET status = ?,
                        result_url = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE agent_request_id = ?
                    """,
                    (status.value, result_url, agent_request_id)
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE parse_requests
                    SET status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE agent_request_id = ?
                    """,
                    (status.value, agent_request_id)
                )

            conn.commit()

            if cursor.rowcount > 0:
                return await self.get_by_agent_id(agent_request_id)
            return None
        finally:
            conn.close()

    async def get_by_agent_id(self, agent_request_id: str) -> Optional[ParseRequest]:
        """Get a parse request by agent request ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM parse_requests WHERE agent_request_id = ?",
                (agent_request_id,)
            )
            row = cursor.fetchone()

            if row:
                return ParseRequest(
                    id=row["id"],
                    discord_message_id=row["discord_message_id"],
                    discord_response_id=row["discord_response_id"],
                    agent_request_id=row["agent_request_id"],
                    status=ParseStatus(row["status"]),
                    result_url=row["result_url"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
            return None
        finally:
            conn.close()

    async def get_by_message_id(self, discord_message_id: int) -> Optional[ParseRequest]:
        """Get a parse request by Discord message ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM parse_requests WHERE discord_message_id = ?",
                (discord_message_id,)
            )
            row = cursor.fetchone()

            if row:
                return ParseRequest(
                    id=row["id"],
                    discord_message_id=row["discord_message_id"],
                    discord_response_id=row["discord_response_id"],
                    agent_request_id=row["agent_request_id"],
                    status=ParseStatus(row["status"]),
                    result_url=row["result_url"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
            return None
        finally:
            conn.close()
