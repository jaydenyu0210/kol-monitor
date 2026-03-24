import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DEFAULT_KOLS = [
    "tussiwe", "BrianRoemmele", "AIBuzzNews", "heyDhavall", "iamfakhrealam", 
    "RAVIKUMARSAHU78", "JaynitMakwana", "ai_for_success", "thetripathi58", 
    "deedydas", "heyshrutimishra", "Parul_Gautam7", "riyazmd774", 
    "socialwithaayan", "LearnWithBishal", "tec_aryan", "Rana_kamran43", 
    "mhdfaran", "TechByMarkandey", "freest_man", "hasantoxr", "shedntcare_", 
    "atulkumarzz", "HeyAbhishekk", "FellMentKE", "HeyNayeem", "swapnakpanda", 
    "avikumart_", "Saboo_Shubham_", "_jaydeepkarale", "AngryTomtweets", 
    "saxxhii_", "s_mohinii", "manishkumar_dev", "_akhaliq", "Sumanth_077", 
    "allen_lattimer", "nrqa__", "TansuYegen", "SarahAnnabels", "SaniBulaAI", 
    "Prathkum", "TheAIColony", "madzadev", "CodeByPoonam", "AndrewBolis"
]

def seed_users():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not found")
        return

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get all users from user_configs
        cur.execute("SELECT DISTINCT user_id as id FROM user_configs")
        users = cur.fetchall()
        print(f"📡 Found {len(users)} users to seed.")

        for user in users:
            uid = user['id']
            print(f"  👤 Seeding user {uid}...")
            
            for handle in DEFAULT_KOLS:
                # Check if exists by name (handle)
                cur.execute("SELECT id FROM kols WHERE user_id = %s AND name = %s", (uid, handle))
                if not cur.fetchone():
                    twitter_url = f"https://x.com/{handle}"
                    cur.execute(
                        "INSERT INTO kols (user_id, name, twitter_url, status) VALUES (%s, %s, %s, 'active')",
                        (uid, handle, twitter_url)
                    )
                    print(f"    ✅ Added @{handle}")
                else:
                    print(f"    ⏭️ Skipped @{handle} (already exists)")
            
            conn.commit()

        print("\n✨ Seeding completed successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    seed_users()
