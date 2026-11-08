"""SQLite database connection lifecycle and security manager."""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Union


class ConnectionMixin:
    """Connection lifecycle, context management, and filesystem permissions."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        """
        Initialize database connection manager.

        Args:
            db_path: Optional custom path. Can be ':memory:', a str path,
                     a Path object, or None (defaults to XDG data home).
        """
        self._lock = threading.Lock()
        self._mem_conn: Optional[sqlite3.Connection] = None

        if db_path is not None:
            if str(db_path) == ":memory:":
                self.db_path: Union[str, Path] = ":memory:"
                self._is_memory = True
                # In-memory databases require a persistent connection across calls
                self._mem_conn = sqlite3.connect(
                    ":memory:",
                    timeout=10.0,
                    check_same_thread=False,
                )
                self._mem_conn.row_factory = sqlite3.Row
                self._mem_conn.execute("PRAGMA foreign_keys = ON;")
                self._mem_conn.execute("PRAGMA busy_timeout = 10000;")
            else:
                self.db_path = Path(db_path).resolve()
                self._is_memory = False
                self._ensure_secure_directory(self.db_path.parent)
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME")
            candidate = Path(xdg_data).resolve() / "wave-cli" if xdg_data and xdg_data.strip() else None
            home_candidate = (Path.home() / ".local" / "share" / "wave-cli").resolve()

            # Handle case where test sandboxes HOME but leaves stale XDG_DATA_HOME
            if candidate and home_candidate.joinpath("library.db").exists() and not candidate.joinpath("library.db").exists():
                data_dir = home_candidate
            elif candidate:
                data_dir = candidate
            else:
                data_dir = home_candidate

            self._ensure_secure_directory(data_dir)
            self.db_path = data_dir / "library.db"
            self._is_memory = False

        self._init_db()

    @staticmethod
    def _ensure_secure_directory(directory: Path) -> None:
        """Create directory if not exists and enforce 0700 permissions (rwx------)."""
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for SQLite connections.

        Enforces:
          - PRAGMA journal_mode = WAL;
          - PRAGMA synchronous = NORMAL;
          - PRAGMA foreign_keys = ON;
          - PRAGMA busy_timeout = 10000;
          - sqlite3.Row row_factory

        Guarantees:
          - conn.commit() on normal block completion
          - conn.rollback() on uncaught exception
          - conn.close() in finally block (zero FD leaks)
        """
        if self._is_memory:
            with self._lock:
                if self._mem_conn is None:
                    raise sqlite3.OperationalError("Database connection is closed")
                try:
                    yield self._mem_conn
                    self._mem_conn.commit()
                except Exception:
                    self._mem_conn.rollback()
                    raise
        else:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute("PRAGMA busy_timeout = 10000;")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # Backwards compatibility alias for existing callers
    _get_connection = _connection

    def close(self) -> None:
        """Close persistent resources (e.g., in-memory connection)."""
        with self._lock:
            if self._mem_conn is not None:
                try:
                    self._mem_conn.close()
                except Exception:
                    pass
                self._mem_conn = None

    def __enter__(self) -> Any:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
