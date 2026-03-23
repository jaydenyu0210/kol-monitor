import os
import psycopg2
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    print("🚀 Starting migration: Adding first_captured_at to twitter_posts...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        # Add first_captured_at if it doesn't exist
        cur.execute("""
            ALTER TABLE twitter_posts 
            ADD COLUMN IF NOT EXISTS first_captured_at TIMESTAMP DEFAULT NOW();
        """)
        
        # Populate first_captured_at from captured_at for existing posts
        cur.execute("""
            UPDATE twitter_posts 
            SET first_captured_at = captured_at 
            WHERE first_captured_at IS NULL;
        """)
        
        conn.commit()
        print("✅ Migration successful: first_captured_at column added.")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    migrate()
