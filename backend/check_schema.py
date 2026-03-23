import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

def check_schema():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    try:
        print("🔍 Checking column types for 'user_id' in 'kols' and 'twitter_posts'...")
        cur.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE column_name = 'user_id' AND table_name IN ('kols', 'twitter_posts', 'users');
        """)
        for row in cur.fetchall():
            print(f"  {row[0]}.{row[1]}: {row[2]}")
            
        print("\n🔍 Checking 'system_status' keys...")
        cur.execute("SELECT key FROM system_status;")
        for row in cur.fetchall():
            print(f"  Key: {row[0]}")
            
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    check_schema()
