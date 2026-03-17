import os
from pathlib import Path

# Load .env file manually to avoid dependencies
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env()

# Database
DB_NAME = os.getenv("DB_NAME", "kol_monitor")
DB_USER = os.getenv("DB_USER", "node")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# Construct DSN
# In Docker Compose, host is usually 'db'. In local setup it's 'localhost' or socket path
if DB_HOST.startswith("/"):
     DB_DSN = f"dbname={DB_NAME} host={DB_HOST}"
else:
     DB_DSN = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

# Twitter
TWITTER_AUTH_TOKEN = os.getenv("TWITTER_AUTH_TOKEN")
TWITTER_CT0 = os.getenv("TWITTER_CT0")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL_MINS", "15"))
SLOW_MO = 3000

# API
API_PORT = int(os.getenv("API_PORT", "3000"))

# Discord
DISCORD_WEBHOOKS = {
    "posts": os.getenv("DISCORD_WEBHOOK_POSTS"),
    "interactions": os.getenv("DISCORD_WEBHOOK_INTERACTIONS"),
    "following": os.getenv("DISCORD_WEBHOOK_FOLLOWING"),
    "followers": os.getenv("DISCORD_WEBHOOK_FOLLOWERS"),
    "metrics": os.getenv("DISCORD_WEBHOOK_METRICS"),
    "heatmap": os.getenv("DISCORD_WEBHOOK_HEATMAP")
}
