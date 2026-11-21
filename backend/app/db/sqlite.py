import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  members INTEGER NOT NULL,
  buy_limit INTEGER,
  highalch INTEGER,
  value INTEGER,
  image_url TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

CREATE TABLE IF NOT EXISTS price_snapshots (
  item_id INTEGER NOT NULL REFERENCES items(id),
  ts INTEGER NOT NULL,
  high INTEGER,
  low INTEGER,
  high_vol INTEGER,
  low_vol INTEGER,
  source TEXT NOT NULL,
  PRIMARY KEY (item_id, ts, source)
);
CREATE INDEX IF NOT EXISTS idx_snap_item_ts ON price_snapshots(item_id, ts DESC);

CREATE TABLE IF NOT EXISTS recipes (
  id TEXT PRIMARY KEY,
  skill TEXT NOT NULL,
  level INTEGER NOT NULL,
  xp REAL NOT NULL DEFAULT 0,
  members INTEGER NOT NULL,
  product_item_id INTEGER NOT NULL,
  product_qty INTEGER NOT NULL,
  materials_json TEXT NOT NULL,
  fee INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS players (
  name TEXT PRIMARY KEY,
  skills_json TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
"""


class Database:
    """Single shared sqlite connection, guarded by a lock (routes run in a
    threadpool; the refresh loop runs on the event loop thread)."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            for col in ("tools_json TEXT", "facilities_json TEXT", "xp REAL NOT NULL DEFAULT 0", "extra_skills_json TEXT"):
                try:
                    self._conn.execute(f"ALTER TABLE recipes ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass  # column already exists
            try:
                self._conn.execute("ALTER TABLE items ADD COLUMN value INTEGER")
            except sqlite3.OperationalError:
                pass  # column already exists
            try:
                self._conn.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            self._conn.commit()

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def executemany(self, sql, seq):
        with self._lock:
            cur = self._conn.executemany(sql, seq)
            self._conn.commit()
            return cur

    def query(self, sql, params=()):
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None
