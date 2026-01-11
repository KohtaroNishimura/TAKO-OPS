import os
import sqlite3

import libsql
from flask import g

APP_DIR = os.path.abspath(os.path.dirname(__file__))
DB_FILE = os.getenv("SQLITE_FILE", os.path.join(APP_DIR, "takoyaki_inventory.db"))
REPLICA_FILE = os.getenv("TURSO_REPLICA_FILE", os.path.join(APP_DIR, "replica.db"))


def _row_to_dict(row, description):
    if row is None or description is None:
        return row
    return {col[0]: row[idx] for idx, col in enumerate(description)}


class _LibsqlCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, *args, **kwargs):
        self._cursor.execute(*args, **kwargs)
        return self

    def executemany(self, *args, **kwargs):
        self._cursor.executemany(*args, **kwargs)
        return self

    def fetchone(self):
        return _row_to_dict(self._cursor.fetchone(), self._cursor.description)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [_row_to_dict(row, self._cursor.description) for row in rows]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _DBProxy:
    def __init__(self, conn, is_libsql):
        self._conn = conn
        self._is_libsql = is_libsql

    def cursor(self, *args, **kwargs):
        cur = self._conn.cursor(*args, **kwargs)
        if self._is_libsql:
            return _LibsqlCursor(cur)
        return cur

    def execute(self, *args, **kwargs):
        cur = self.cursor()
        cur.execute(*args, **kwargs)
        return cur

    def executemany(self, *args, **kwargs):
        cur = self.cursor()
        cur.executemany(*args, **kwargs)
        return cur

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def commit(self):
        self._conn.commit()
        if hasattr(self._conn, "sync"):
            self._conn.sync()


def get_db():
    if "db" in g:
        return g.db

    turso_url = os.getenv("TURSO_DATABASE_URL")
    turso_token = os.getenv("TURSO_AUTH_TOKEN")
    use_libsql = bool(turso_url and turso_token)

    if use_libsql:
        conn = libsql.connect(
            REPLICA_FILE, sync_url=turso_url, auth_token=turso_token
        )
        conn.sync()
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON;")

    g.db = _DBProxy(conn, is_libsql=use_libsql)
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def commit_and_sync():
    db = get_db()
    db.commit()
