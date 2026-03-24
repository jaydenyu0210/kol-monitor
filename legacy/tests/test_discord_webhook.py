import psycopg2
import psycopg2.extras
from config import DB_DSN
from discord_push import send_discord
from datetime import datetime

def test_webhooks(user_id=1):
    try:
        db = psycopg2.connect(DB_DSN)
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT discord_webhook_posts, discord_webhook_interactions, discord_webhook_heatmap, discord_webhook_following, discord_webhook_followers FROM users WHERE id = %s", (user_id,))
        webhooks = cur.fetchone()
        db.close()
        
        if not webhooks:
            print("No webhooks found for user", user_id)
            return
            
        embed = {
            "title": "✅ KOL Monitor Test Notification",
            "description": "If you are seeing this message, your Discord webhook integration is working perfectly!",
            "color": 0x00FF00,
            "timestamp": datetime.now().isoformat()
        }

        any_sent = False
        for key, url in webhooks.items():
            if url:
                print(f"Testing {key}...")
                success = send_discord(url, embed)
                if success:
                    print(f"  ✅ Successfully sent test message to {key}")
                    any_sent = True
                else:
                    print(f"  ❌ Failed to send to {key}")
        
        if not any_sent:
            print("No webhooks were configured or all sends failed.")
            
    except Exception as e:
        print("Error during test:", e)

if __name__ == "__main__":
    test_webhooks()
