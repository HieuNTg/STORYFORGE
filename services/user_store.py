"""SQLite-backed user storage with password hashing. Thread-safe singleton."""
import hashlib
import hmac as _hmac
import logging
import os
import sqlite3
import threading
import uuid

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "users.db")
_LOCK = threading.Lock()
_instance = None


class UserStore:
    """Thread-safe SQLite user store."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = os.path.abspath(db_path)
        self._local = threading.local()
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """Return a per-thread connection (created on demand)."""
        if not getattr(self._local, "conn", None):
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        with _LOCK:
            conn = self._conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id   TEXT PRIMARY KEY,
                    username  TEXT UNIQUE NOT NULL,
                    pw_hash   TEXT NOT NULL,
                    pw_salt   TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """PBKDF2-HMAC-SHA256, 260k iterations."""
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            260_000,
        )
        return dk.hex()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_user(self, username: str, password: str) -> str:
        """Create a new user. Returns user_id. Raises ValueError if username taken."""
        user_id = str(uuid.uuid4())
        salt = uuid.uuid4().hex
        pw_hash = self._hash_password(password, salt)
        with _LOCK:
            try:
                self._conn().execute(
                    "INSERT INTO users (user_id, username, pw_hash, pw_salt) VALUES (?,?,?,?)",
                    (user_id, username, pw_hash, salt),
                )
                self._conn().commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Username '{username}' already exists")
        logger.info(f"User created: {username} ({user_id})")
        return user_id

    def authenticate(self, username: str, password: str) -> "str | None":
        """Verify credentials. Returns user_id on success, None on failure."""
        row = self._conn().execute(
            "SELECT user_id, pw_hash, pw_salt FROM users WHERE username=?", (username,)
        ).fetchone()
        if not row:
            return None
        expected = self._hash_password(password, row["pw_salt"])
        if _hmac.compare_digest(expected, row["pw_hash"]):
            return row["user_id"]
        return None

    def get_user(self, user_id: str) -> "dict | None":
        """Return user dict {user_id, username, created_at} or None."""
        row = self._conn().execute(
            "SELECT user_id, username, created_at FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_store() -> UserStore:
    """Singleton accessor."""
    global _instance
    if _instance is None:
        with _LOCK:
            if _instance is None:
                _instance = UserStore()
    return _instance
