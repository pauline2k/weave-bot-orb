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
    grist_record_id: Optional[int]  # Grist row ID for editorial updates
    created_at: str
    updated_at: str


class Database:
    def __init__(self, db_path: str = "weave_bot.db"):
        import logging
        import os
        logger = logging.getLogger(__name__)

        self.db_path = db_path
        abs_path = os.path.abspath(db_path)
        logger.info(f'Database path: {db_path}')
        logger.info(f'Absolute database path: {abs_path}')
        logger.info(f'Current working directory: {os.getcwd()}')
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
                    grist_record_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for quick lookups by agent_request_id
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_request_id
                ON parse_requests(agent_request_id)
            """)

            # Index for quick lookups by discord_response_id (for reply detection)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_discord_response_id
                ON parse_requests(discord_response_id)
            """)

            # Migration: Add grist_record_id column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(parse_requests)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'grist_record_id' not in columns:
                conn.execute("ALTER TABLE parse_requests ADD COLUMN grist_record_id INTEGER")

            conn.commit()
        finally:
            conn.close()

    async def create_request(
        self,
        discord_message_id: int,
        discord_response_id: int
    ) -> int:
        """Create a new parse request."""
        import logging
        logger = logging.getLogger(__name__)

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
            row_id = cursor.lastrowid
            logger.info(f'Created request in DB: id={row_id}, discord_message_id={discord_message_id}, discord_response_id={discord_response_id}')
            return row_id
        finally:
            conn.close()

    async def update_agent_id(
        self,
        discord_message_id: int,
        agent_request_id: str
    ) -> bool:
        """Update the agent request ID for a parse request."""
        import logging
        logger = logging.getLogger(__name__)

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
            updated = cursor.rowcount > 0
            logger.info(f'Updated agent_id in DB: discord_message_id={discord_message_id}, agent_request_id={agent_request_id}, rows_updated={cursor.rowcount}')
            return updated
        finally:
            conn.close()

    async def update_status(
        self,
        agent_request_id: str,
        status: ParseStatus,
        result_url: Optional[str] = None
    ) -> Optional[ParseRequest]:
        """Update the status of a parse request by agent ID."""
        import logging
        logger = logging.getLogger(__name__)

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
            logger.info(f'Updated status in DB: agent_request_id={agent_request_id}, status={status.value}, rows_updated={cursor.rowcount}')

            if cursor.rowcount > 0:
                result = await self.get_by_agent_id(agent_request_id)
                logger.info(f'Found request after update: {result}')
                return result
            else:
                logger.warning(f'No rows updated for agent_request_id={agent_request_id}')
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
                    grist_record_id=row["grist_record_id"],
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
                    grist_record_id=row["grist_record_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
            return None
        finally:
            conn.close()

    async def get_by_response_id(self, discord_response_id: int) -> Optional[ParseRequest]:
        """Get a parse request by Discord response ID (bot's reply message)."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM parse_requests WHERE discord_response_id = ?",
                (discord_response_id,)
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
                    grist_record_id=row["grist_record_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                )
            return None
        finally:
            conn.close()

    async def update_grist_record_id(
        self,
        agent_request_id: str,
        grist_record_id: int
    ) -> bool:
        """Update the Grist record ID for a parse request."""
        import logging
        logger = logging.getLogger(__name__)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                UPDATE parse_requests
                SET grist_record_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE agent_request_id = ?
                """,
                (grist_record_id, agent_request_id)
            )
            conn.commit()
            updated = cursor.rowcount > 0
            logger.info(f'Updated grist_record_id in DB: agent_request_id={agent_request_id}, grist_record_id={grist_record_id}, rows_updated={cursor.rowcount}')
            return updated
        finally:
            conn.close()
