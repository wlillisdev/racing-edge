"""
db.py — MySQL database connection layer for PythonAnywhere.

Design principles
-----------------
- A module-level singleton _db_instance holds the active DatabaseManager so
  that repeated calls to get_db() reuse the same object across a script run.
- Connection drops (PythonAnywhere MySQL times out idle connections) are
  detected via ping() and the connection is transparently re-established.
- All rows are returned as dicts (column-name-keyed) via DictCursor so
  callers never index by position.
- Every database error is logged before re-raising to give a visible audit
  trail without swallowing the exception.
- execute() / execute_many() commit automatically; fetch_*() never commit.
"""

from __future__ import annotations

from typing import Optional

import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.cursor import MySQLCursorDict

from src.config import get_config
from src.helpers import log


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------

class DatabaseManager:
    """Manages a persistent MySQL connection with automatic reconnection."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._conn: Optional[mysql.connector.MySQLConnection] = None
        # Establish initial connection eagerly so failures surface early.
        self._connect()

    # ------------------------------------------------------------------
    # Internal connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Open (or reopen) the MySQL connection."""
        try:
            self._conn = mysql.connector.connect(
                host=self._host,
                port=self._port,
                database=self._database,
                user=self._user,
                password=self._password,
                # Keep the connection alive across long gaps between queries.
                connection_timeout=30,
                # Use utf8mb4 so emoji / extended characters in horse names
                # are stored correctly.
                charset="utf8mb4",
                collation="utf8mb4_unicode_ci",
                # Raise an exception rather than silently returning None rows.
                raise_on_warnings=False,
                # Auto-reconnect is deliberately NOT used here — we handle it
                # ourselves via ping() so we have visibility in the logs.
                autocommit=False,
            )
            log(
                f"DatabaseManager: connected to {self._database} at {self._host}:{self._port}"
            )
        except MySQLError as exc:
            log(f"DatabaseManager: connection failed — {exc}", "ERROR")
            raise

    def _ensure_connection(self) -> mysql.connector.MySQLConnection:
        """Return a live connection, reconnecting if the socket has gone stale.

        PythonAnywhere's MySQL proxy drops idle connections after ~5 minutes.
        We use ping(reconnect=False) to detect a dead socket and reconnect
        manually so that we control the error logging.
        """
        if self._conn is None:
            log("DatabaseManager: no connection present — connecting", "WARNING")
            self._connect()
            return self._conn  # type: ignore[return-value]

        try:
            self._conn.ping(reconnect=False, attempts=1, delay=0)
        except MySQLError:
            log(
                "DatabaseManager: stale connection detected — reconnecting",
                "WARNING",
            )
            self._conn = None
            self._connect()

        return self._conn  # type: ignore[return-value]

    def get_connection(self) -> mysql.connector.MySQLConnection:
        """Return the active (and live) MySQL connection object.

        Callers that need direct cursor access (e.g. for streaming large
        result sets) should use this, but prefer the execute/fetch helpers
        for normal usage.
        """
        return self._ensure_connection()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a single DML statement and commit.

        Args:
            sql:    SQL statement with %s placeholders.
            params: Tuple of bind parameters.

        Returns:
            Number of rows affected (rowcount).

        Raises:
            MySQLError: On any database error (after logging).
        """
        conn = self._ensure_connection()
        cursor: MySQLCursorDict = conn.cursor()
        try:
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount
        except MySQLError as exc:
            conn.rollback()
            log(f"DatabaseManager.execute: error — {exc}\nSQL: {sql}\nParams: {params}", "ERROR")
            raise
        finally:
            cursor.close()

    def execute_many(self, sql: str, params_list: list[tuple]) -> int:
        """Execute a bulk DML statement and commit.

        Args:
            sql:         SQL statement with %s placeholders.
            params_list: List of parameter tuples, one per row.

        Returns:
            Total number of rows affected.

        Raises:
            MySQLError: On any database error (after logging).
        """
        if not params_list:
            return 0

        conn = self._ensure_connection()
        cursor: MySQLCursorDict = conn.cursor()
        try:
            cursor.executemany(sql, params_list)
            conn.commit()
            return cursor.rowcount
        except MySQLError as exc:
            conn.rollback()
            log(
                f"DatabaseManager.execute_many: error — {exc}\nSQL: {sql}\n"
                f"First params: {params_list[0] if params_list else '()'}",
                "ERROR",
            )
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a SELECT and return all rows as a list of dicts.

        Returns [] on no results.  Never commits.

        Raises:
            MySQLError: On any database error (after logging).
        """
        conn = self._ensure_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return rows if rows else []
        except MySQLError as exc:
            log(f"DatabaseManager.fetch_all: error — {exc}\nSQL: {sql}\nParams: {params}", "ERROR")
            raise
        finally:
            cursor.close()

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Execute a SELECT and return the first row as a dict, or None.

        Never commits.

        Raises:
            MySQLError: On any database error (after logging).
        """
        conn = self._ensure_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)
            return cursor.fetchone()
        except MySQLError as exc:
            log(f"DatabaseManager.fetch_one: error — {exc}\nSQL: {sql}\nParams: {params}", "ERROR")
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def table_exists(self, table_name: str) -> bool:
        """Return True if *table_name* exists in the current database."""
        row = self.fetch_one(
            "SELECT COUNT(*) AS cnt "
            "FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s",
            (self._database, table_name),
        )
        return bool(row and row["cnt"] > 0)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection gracefully."""
        if self._conn is not None:
            try:
                self._conn.close()
                log("DatabaseManager: connection closed")
            except MySQLError as exc:
                log(f"DatabaseManager.close: error — {exc}", "WARNING")
            finally:
                self._conn = None


# ---------------------------------------------------------------------------
# Module-level singleton + factory
# ---------------------------------------------------------------------------

_db_instance: Optional[DatabaseManager] = None


def get_db() -> DatabaseManager:
    """Return the module-level DatabaseManager singleton.

    The singleton is created on first call using environment configuration
    and reused for the lifetime of the process.  This avoids opening a new
    MySQL connection on every helper-function call across a pipeline run.

    Example::

        db = get_db()
        rows = db.fetch_all("SELECT * FROM races WHERE race_date = %s", (today,))
    """
    global _db_instance
    if _db_instance is None:
        cfg = get_config()
        _db_instance = DatabaseManager(
            host=cfg.db_host,
            port=cfg.db_port,
            database=cfg.db_name,
            user=cfg.db_user,
            password=cfg.db_pass,
        )
    return _db_instance
