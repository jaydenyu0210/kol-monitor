"""
Supabase Connection Pool for KOL Monitor Pro.
Uses psycopg2 ThreadedConnectionPool connected to Supabase's
connection pooler on port 6543 (Transaction Mode).
"""
import os
from psycopg2 import pool

# Supabase connection string from Railway env
# Format: postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:6543/postgres
DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None


def get_pool():
    """Lazily initialize and return the connection pool."""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Set it to your Supabase connection pooler URL (port 6543)."
            )
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


def get_db():
    """Get a connection from the pool."""
    return get_pool().getconn()


def release_db(conn):
    """Return a connection to the pool."""
    if conn:
        get_pool().putconn(conn)
