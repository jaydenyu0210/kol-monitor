"""
Supabase Connection Pool for KOL Monitor Pro.
Uses psycopg2 ThreadedConnectionPool connected to Supabase's
connection pooler on port 6543 (Transaction Mode).
"""
import os
from psycopg2 import pool

# Supabase connection string from Railway env
# Format: postgresql://postgres.[ref]:[password]@db.[ref].supabase.co:6543/postgres
import os
import threading
from psycopg2 import pool

# Supabase connection string from Railway env
DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None
_lock = threading.Lock()


def get_pool():
    """Lazily initialize and return the connection pool (Thread-safe)."""
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError(
                        "DATABASE_URL is not set. "
                        "Set it to your Supabase connection pooler URL (port 6543)."
                    )
                _pool = pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=20, # Increased maxconn for concurrent requests
                    dsn=DATABASE_URL,
                )
    return _pool


def get_db():
    """Get a connection from the pool."""
    return get_pool().getconn()


def release_db(conn):
    """Return a connection to the pool."""
    if conn:
        try:
            get_pool().putconn(conn)
        except pool.PoolError as e:
            print(f"⚠️ PoolError in release_db: {e}")
        except Exception as e:
            print(f"⚠️ Error in release_db: {e}")
