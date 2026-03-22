"""
KOL Monitor Scheduler - Runs scraping jobs on schedule and pushes to Discord.
"""
import asyncio
import subprocess
import sys
import os
import json
import psycopg2
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import SCRAPE_INTERVAL, DATABASE_URL

def update_system_status(key, value_updates):
    try:
        # Add Instance identification to help user distinguish between local and ghost instance
        if 'current_activity' in value_updates:
            activity = value_updates['current_activity']
            if activity and 'Monitor Idle' not in activity:
                value_updates['current_activity'] = f"{activity} (Instance: Docker-Mac)"
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # 1. Fetch current value to merge
        cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
        row = cur.fetchone()
        status = row[0] if row else {}
        
        # 2. Merge updates
        status.update(value_updates)
        
        # 3. Save back
        cur.execute("""
            INSERT INTO system_status (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(status)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Error updating system_status ({key}): {e}")

def run_twitter_scraper():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚀 [SCHEDULED SCRAPE] Starting...")
    
    # Report that we are actively running
    update_system_status('twitter_scraper_status', {
        'is_running': True,
        'last_start_at': datetime.now(timezone.utc).isoformat()
    })

    try:
        # Use Popen to stream output live with a prefix
        process = subprocess.Popen(
            [sys.executable, "-u", "/app/twitter_scraper.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in process.stdout:
            print(f"[SCHEDULED SCRAPE] {line.strip()}", flush=True)
            
        process.wait(timeout=3600)
    except Exception as e:
        print(f"❌ [SCHEDULED SCRAPE] Error: {e}")
    finally:
        # Trigger Discord Pushes sequentially immediately AFTER scrape finishes
        for job in ["posts", "following", "followers", "heatmap", "interactions"]:
            run_discord_push(job)
        
        # Report that we are finished
        update_system_status('twitter_scraper_status', {
            'is_running': False,
            'current_activity': 'Monitor Idle - All KOLs up to date'
        })

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

def update_next_run_at():
    """Safety sync: ensure next_run_at is in DB even if scheduler is starting up after crash."""
    try:
        next_run = datetime.now(timezone.utc) + timedelta(minutes=SCRAPE_INTERVAL)
        update_system_status('twitter_scraper_status', {
            'next_run_at': next_run.isoformat(),
            'interval_mins': SCRAPE_INTERVAL,
            'is_running': False, # Startup safety: insure we are not marked as running on boot
            'current_activity': 'Monitor Idle - All KOLs up to date'
        })
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🕒 Next scheduled scrape at: {next_run.strftime('%H:%M:%S')} UTC")
    except Exception as e:
        print(f"⚠️ Error updating initial next_run: {e}")

async def sync_scheduler_status(scheduler):
    while True:
        try:
            job = scheduler.get_job('twitter_scraper')
            if job and job.next_run_time:
                update_system_status('twitter_scraper_status', {
                    'next_run_at': job.next_run_time.isoformat(),
                    'interval_mins': SCRAPE_INTERVAL
                })
        except Exception as e:
            print(f"⚠️ Status sync error: {e}")
        await asyncio.sleep(30) # Update every 30s

async def main():
    scheduler = AsyncIOScheduler()

    # Scraper runs every SCRAPE_INTERVAL minutes and triggers Discord pushes sequentially
    scheduler.add_job(run_twitter_scraper, 'interval', minutes=SCRAPE_INTERVAL, id='twitter_scraper')

    # DM Scheduler runs every SCRAPE_INTERVAL minutes
    scheduler.add_job(run_dm_scheduler, 'interval', minutes=SCRAPE_INTERVAL, id='dm_scheduler_job')

    scheduler.start()
    print(f"📅 KOL Monitor Scheduler Started ({SCRAPE_INTERVAL}m Mode)!")
    
    # Initial status cleanup and sync for the frontend
    update_next_run_at()

    # Start the background sync task
    asyncio.create_task(sync_scheduler_status(scheduler))

    try:
        while True: await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
