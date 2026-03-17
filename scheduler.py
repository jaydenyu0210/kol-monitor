"""
KOL Monitor Scheduler - Runs scraping jobs on schedule and pushes to Discord.
"""
import asyncio
import subprocess
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import SCRAPE_INTERVAL

def run_twitter_scraper():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running Twitter scraper (5m interval)...")
    try:
        subprocess.run([sys.executable, "/data/.openclaw/workspace/kol-monitor/twitter_scraper.py"], timeout=600)
    except Exception as e:
        print(f"❌ Twitter scraper error: {e}")

def run_discord_push_posts():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Pushing NEW POSTS to Discord...")
    try:
        subprocess.run([sys.executable, "/data/.openclaw/workspace/kol-monitor/discord_push.py", "posts", "5"], timeout=60)
    except Exception as e:
        print(f"❌ Discord push error: {e}")

def run_discord_push_metrics():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Pushing FOLLOWERS/FOLLOWING to Discord...")
    try:
        subprocess.run([sys.executable, "/data/.openclaw/workspace/kol-monitor/discord_push.py", "metrics", "5"], timeout=60)
    except Exception as e:
        print(f"❌ Discord push error: {e}")


def run_discord_push_heatmap():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Pushing TRENDING SURGE to Discord...")
    try:
        subprocess.run([sys.executable, "/data/.openclaw/workspace/kol-monitor/discord_push.py", "heatmap", "5"], timeout=60)
    except Exception as e:
        print(f"❌ Discord push error: {e}")

async def main():

    scheduler = AsyncIOScheduler()
    
    # Scrapers (Dynamic interval from config)
    scheduler.add_job(run_twitter_scraper, 'interval', minutes=SCRAPE_INTERVAL, id='twitter_scraper')
    
    # Push Tasks
    scheduler.add_job(run_discord_push_posts, 'interval', minutes=SCRAPE_INTERVAL, seconds=30, id='discord_push_posts')
    scheduler.add_job(run_discord_push_metrics, 'interval', minutes=SCRAPE_INTERVAL, id='discord_push_metrics')
    scheduler.add_job(run_discord_push_heatmap, 'interval', minutes=SCRAPE_INTERVAL, seconds=60, id='discord_push_heatmap')
    
    scheduler.start()
    print("📅 KOL Monitor Scheduler Started (Balanced 15m Mode)!")
    print("   - All tasks run every 15 minutes")
    print("   - Trending reports pushed to interactions channel")
    
    try:
        while True: await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
