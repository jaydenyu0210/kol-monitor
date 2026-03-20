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
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running Twitter scraper...")
    try:
        subprocess.run([sys.executable, "/app/twitter_scraper.py"], timeout=600)
    except Exception as e:
        print(f"❌ Twitter scraper error: {e}")

def run_dm_scheduler():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running DM Scheduler...")
    try:
        subprocess.run([sys.executable, "/app/dm_scheduler.py"], timeout=600)
    except Exception as e:
        print(f"❌ DM Scheduler error: {e}")

def run_discord_push(job_type):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Pushing {job_type.upper()} to Discord...")
    try:
        subprocess.run([sys.executable, "/app/discord_push.py", job_type], timeout=120)
    except Exception as e:
        print(f"❌ Discord push error ({job_type}): {e}")

async def main():
    scheduler = AsyncIOScheduler()

    # Scraper runs every SCRAPE_INTERVAL minutes
    scheduler.add_job(run_twitter_scraper, 'interval', minutes=SCRAPE_INTERVAL, id='twitter_scraper')

    # Discord push jobs — all run every SCRAPE_INTERVAL minutes, staggered by seconds
    scheduler.add_job(lambda: run_discord_push("posts"),        'interval', minutes=SCRAPE_INTERVAL, seconds=30, id='push_posts')
    scheduler.add_job(lambda: run_discord_push("following"),    'interval', minutes=SCRAPE_INTERVAL, seconds=40, id='push_following')
    scheduler.add_job(lambda: run_discord_push("followers"),    'interval', minutes=SCRAPE_INTERVAL, seconds=50, id='push_followers')
    scheduler.add_job(lambda: run_discord_push("heatmap"),      'interval', minutes=SCRAPE_INTERVAL, seconds=60, id='push_heatmap')
    scheduler.add_job(lambda: run_discord_push("interactions"), 'interval', minutes=SCRAPE_INTERVAL, seconds=70, id='push_interactions')

    # DM Scheduler runs every 5 minutes specifically
    scheduler.add_job(run_dm_scheduler, 'interval', minutes=5, id='dm_scheduler_job')

    scheduler.start()
    print(f"📅 KOL Monitor Scheduler Started ({SCRAPE_INTERVAL}m Mode)!")
    print(f"   - Scraper runs every {SCRAPE_INTERVAL} minutes")
    print(f"   - 5 Discord channels updated every {SCRAPE_INTERVAL} minutes")
    print(f"   - Channels: posts, following, followers, heatmap, interactions")
    print(f"   - DM Scheduler runs every 5 minutes")

    try:
        while True: await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
