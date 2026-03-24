"""
KOL Monitor Scheduler - Runs scraping jobs on schedule and pushes to Discord.
"""
import asyncio
import subprocess
import sys
import os
import json
import psycopg2
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import SCRAPE_INTERVAL, DATABASE_URL

def update_system_status(key, value_updates, user_id=None):
    try:
        if user_id and key == 'twitter_scraper_status':
            key = f'twitter_scraper_status_{user_id}'
            
        # Add Instance identification to help user distinguish between local and ghost instance
        env_name = os.getenv("ENVIRONMENT_NAME", "Local")
        if 'current_activity' in value_updates:
            activity = value_updates['current_activity']
            if activity:
                value_updates['current_activity'] = f"{activity} (Instance: {env_name})"
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # 1. Fetch current value to merge
        cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
        row = cur.fetchone()
        status = row[0] if row else {}
        
        # 2. Merge updates
        status.update(value_updates)
        
        # 3. Handle log history (Last 50 lines)
        if user_id and 'current_activity' in value_updates:
            logs = status.get('logs', [])
            msg = value_updates['current_activity']
            ts = datetime.now().strftime('%H:%M:%S')
            # Avoid repeating the exact same timestamped message
            if not logs or not logs[-1].endswith(msg):
                logs.append(f"[{ts}] {msg}")
                status['logs'] = logs[-50:]
        
        # 4. Save back
        cur.execute("""
            INSERT INTO system_status (key, value, updated_at, user_id)
            VALUES (%s, %s, NOW(), %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW(), user_id = EXCLUDED.user_id
        """, (key, json.dumps(status), user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Error updating system_status ({key}): {e}")

def run_twitter_scraper():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚀 [SCHEDULED SCRAPE] Initializing multi-tenant cycle...")
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Only scrape for users who have active KOLs AND configured Twitter credentials
        cur.execute("""
            SELECT DISTINCT k.user_id 
            FROM kols k
            JOIN user_configs uc ON k.user_id = uc.user_id
            WHERE k.status = 'active' 
              AND uc.twitter_auth_token IS NOT NULL 
              AND uc.twitter_auth_token != ''
        """)
        users = [str(r[0]) for r in cur.fetchall()]
        conn.close()
        
        if not users:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️ [SCHEDULED SCRAPE] No active users with credentials found. Skipping.")
            return

        for user_id in users:
            update_system_status('twitter_scraper_status', {
                'is_running': True,
                'last_start_at': datetime.now(timezone.utc).isoformat(),
                'current_activity': 'Initializing profile scrape...'
            }, user_id=user_id)
    except Exception as e:
        print(f"⚠️ Scheduler status error: {e}")

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
        
        # Report that we are finished for ALL users
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
            users = [str(r[0]) for r in cur.fetchall()]
            conn.close()
            
            for user_id in users:
                update_system_status('twitter_scraper_status', {
                    'is_running': False,
                    'current_activity': 'Monitor Idle - All KOLs up to date'
                }, user_id=user_id)
        except Exception as e:
            print(f"⚠️ Scheduler status completion error: {e}")

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

def update_next_run_at(sched=None):
    """Safety sync: ensure next_run_at is in DB even if scheduler is starting up after crash."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🕒 Performing startup schedule sync...")
    try:
        next_run_iso = None
        # IF we have a running scheduler, try to get the real job time
        if sched:
            job = sched.get_job('twitter_scraper')
            if job and job.next_run_time:
                # Ensure the next run time isn't further away than the interval allows (stale state safety)
                max_future = datetime.now(timezone.utc) + timedelta(minutes=SCRAPE_INTERVAL + 1)
                if job.next_run_time > max_future:
                    print(f"⚠️  APScheduler job time ({job.next_run_time}) is too far in future. Capping to {SCRAPE_INTERVAL}m.")
                    next_run_iso = max_future.isoformat()
                else:
                    next_run_iso = job.next_run_time.isoformat()
        
        if not next_run_iso:
            # Fallback/Default for startup
            next_run = datetime.now(timezone.utc) + timedelta(minutes=SCRAPE_INTERVAL)
            next_run_iso = next_run.isoformat()

        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
            users = [str(r[0]) for r in cur.fetchall()]
            conn.close()
            
            for user_id in users:
                update_system_status('twitter_scraper_status', {
                    'next_run_at': next_run_iso,
                    'interval_mins': SCRAPE_INTERVAL,
                    'is_running': False, 
                    'current_activity': 'Monitor Idle - All KOLs up to date'
                }, user_id=user_id)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Initial next_run_at set to {next_run_iso} for {len(users)} users.")
        except Exception as e:
            print(f"⚠️ Error updating initial user next_run: {e}")
    except Exception as e:
        print(f"⚠️ Error in update_next_run_at: {e}")

async def sync_scheduler_status(scheduler):
    while True:
        try:
            job = scheduler.get_job('twitter_scraper')
            if job and job.next_run_time:
                next_run_iso = job.next_run_time.isoformat()
                
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
                users = [str(r[0]) for r in cur.fetchall()]
                conn.close()
                
                for user_id in users:
                    update_system_status('twitter_scraper_status', {
                        'next_run_at': next_run_iso,
                        'interval_mins': SCRAPE_INTERVAL
                    }, user_id=user_id)
        except Exception as e:
            print(f"⚠️ Status sync error: {e}")
        await asyncio.sleep(30) # Update every 30s

async def main():
    scheduler = AsyncIOScheduler()

    # Handle Scraper Toggle
    enabled = os.getenv("SCRAPER_ENABLED", "true").lower() == "true"
    if enabled:
        # Scraper runs every SCRAPE_INTERVAL minutes and triggers Discord pushes sequentially
        scheduler.add_job(run_twitter_scraper, 'interval', minutes=SCRAPE_INTERVAL, id='twitter_scraper')
        # DM Scheduler runs every SCRAPE_INTERVAL minutes
        scheduler.add_job(run_dm_scheduler, 'interval', minutes=SCRAPE_INTERVAL, id='dm_scheduler_job')
        scheduler.start()
        print(f"📅 KOL Monitor Scheduler Started ({SCRAPE_INTERVAL}m Mode) [Env: {os.getenv('ENVIRONMENT_NAME', 'Local')}]")
    else:
        print(f"⏸️  KOL Monitor Scheduler DISABLED via SCRAPER_ENABLED=false [Env: {os.getenv('ENVIRONMENT_NAME', 'Local')}]")
        update_system_status('twitter_scraper_status', {
            'is_running': False,
            'current_activity': f'Scheduler Disabled (Instance: {os.getenv("ENVIRONMENT_NAME", "Local")})',
            'next_run_at': None
        })
    
    # Initial status cleanup and sync for the frontend
    update_next_run_at(scheduler)

    # Start the background sync task
    asyncio.create_task(sync_scheduler_status(scheduler))

    try:
        while True: await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
