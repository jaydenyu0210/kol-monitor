"""
KOL Monitor Scheduler - Runs scraping jobs on schedule and pushes to Discord.
"""
import asyncio
import subprocess
import sys
import os
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import SCRAPE_INTERVAL, DATABASE_URL

def make_status_key(user_id=None):
    env_suffix = os.getenv("ENVIRONMENT_NAME", "Local").replace(" ", "_").lower()
    base = "twitter_scraper_status"
    if env_suffix:
        base = f"{base}_{env_suffix}"
    if user_id:
        base = f"{base}_{user_id}"
    return base

def update_system_status(key, value_updates, user_id=None):
    try:
        if key == 'twitter_scraper_status':
            key = make_status_key(user_id)
            
        # Add Instance identification to help user distinguish between local and ghost instance
        env_name = os.getenv("ENVIRONMENT_NAME", "Local")
        if 'current_activity' in value_updates:
            activity = value_updates['current_activity']
            if activity:
                value_updates['current_activity'] = f"{activity} (Instance: {env_name})"
        value_updates['instance'] = env_name
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
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Only scrape for users who have active KOLs AND configured Twitter credentials
        cur.execute("""
            SELECT DISTINCT k.user_id, COALESCE(uc.scrape_interval_mins, %s) AS interval_mins
            FROM kols k
            JOIN user_configs uc ON k.user_id = uc.user_id
            WHERE k.status = 'active' 
              AND uc.twitter_auth_token IS NOT NULL 
              AND uc.twitter_auth_token != ''
        """, (SCRAPE_INTERVAL,))
        users = [(str(r[0]), int(r[1])) for r in cur.fetchall()]
        conn.close()
        
        if not users:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️ [SCHEDULED SCRAPE] No active users with credentials found. Skipping.")
            return
    except Exception as e:
        print(f"⚠️ Scheduler status error: {e}")
        return

    # Determine which users are due based on their own interval
    due_users = []
    now = datetime.now(timezone.utc)
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for user_id, interval_mins in users:
            cur.execute("SELECT value FROM system_status WHERE key = %s", (make_status_key(user_id),))
            row = cur.fetchone()
            status = row['value'] if row else {}
            next_run_at = status.get('next_run_at')
            last_start_at = status.get('last_start_at')
            is_running = status.get('is_running', False)
            tolerance = timedelta(seconds=2)  # tiny drift allowance

            next_run_dt = None
            if next_run_at:
                try:
                    next_run_dt = datetime.fromisoformat(next_run_at)
                except Exception:
                    next_run_dt = None
            if not next_run_dt and last_start_at:
                try:
                    next_run_dt = datetime.fromisoformat(last_start_at) + timedelta(minutes=interval_mins)
                except Exception:
                    next_run_dt = None
            if not next_run_dt:
                next_run_dt = now + timedelta(minutes=interval_mins)
                update_system_status('twitter_scraper_status', {
                    'next_run_at': next_run_dt.isoformat(),
                    'interval_mins': interval_mins,
                    'is_running': False,
                    'current_activity': f'Monitor Idle - Next run in {interval_mins}m'
                }, user_id=user_id)

            # If already running, just advance the timer cycle and skip starting a new run
            if is_running:
                if now >= next_run_dt:
                    while next_run_dt <= now:
                        next_run_dt += timedelta(minutes=interval_mins)
                    update_system_status('twitter_scraper_status', {
                        'next_run_at': next_run_dt.isoformat(),
                        'interval_mins': interval_mins
                    }, user_id=user_id)
                continue

            # Only start when timer has fully elapsed
            if next_run_dt and now >= (next_run_dt - tolerance):
                next_cycle = next_run_dt + timedelta(minutes=interval_mins)
                while next_cycle <= now:
                    next_cycle += timedelta(minutes=interval_mins)
                due_users.append((user_id, interval_mins))
                update_system_status('twitter_scraper_status', {
                    'is_running': True,
                    'last_start_at': now.isoformat(),
                    'current_activity': 'Initializing profile scrape...',
                    'interval_mins': interval_mins,
                    'next_run_at': next_cycle.isoformat()
                }, user_id=user_id)
        conn.close()
    except Exception as e:
        print(f"⚠️ Scheduler status evaluation error: {e}")
        return

    if not due_users:
        return

    try:
        env = os.environ.copy()
        env["LIMIT_TO_USER_IDS"] = ",".join([u for u, _ in due_users])
        # Use Popen to stream output live with a prefix
        process = subprocess.Popen(
            [sys.executable, "-u", "/app/twitter_scraper.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
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
        
        # Report that we are finished for processed users
        try:
            now_done = datetime.now(timezone.utc)
            for user_id, interval_mins in due_users:
                # Preserve the pre-set cycle; if it's in the past, advance by interval until future
                next_run = None
                try:
                    conn = psycopg2.connect(DATABASE_URL)
                    cur = conn.cursor()
                    cur.execute("SELECT value FROM system_status WHERE key = %s", (make_status_key(user_id),))
                    row = cur.fetchone()
                    status = row[0] if row else {}
                    nr = status.get('next_run_at')
                    if nr:
                        try:
                            next_run = datetime.fromisoformat(nr)
                        except Exception:
                            next_run = None
                    conn.close()
                except Exception:
                    pass
                if not next_run:
                    next_run = now_done + timedelta(minutes=interval_mins)
                while next_run <= now_done:
                    next_run += timedelta(minutes=interval_mins)

                update_system_status('twitter_scraper_status', {
                    'is_running': False,
                    'current_activity': 'Monitor Idle - All KOLs up to date',
                    'next_run_at': next_run.isoformat(),
                    'interval_mins': interval_mins
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
    """Safety sync: ensure next_run_at is present per-user even if scheduler is starting up after crash."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🕒 Performing startup schedule sync...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT DISTINCT k.user_id, COALESCE(uc.scrape_interval_mins, %s) AS interval_mins
            FROM kols k
            JOIN user_configs uc ON k.user_id = uc.user_id
            WHERE k.status = 'active'
        """, (SCRAPE_INTERVAL,))
        users = [(str(r['user_id']), int(r['interval_mins'])) for r in cur.fetchall()]
        conn.close()
        
        now = datetime.now(timezone.utc)
        for user_id, interval_mins in users:
            next_run_iso = (now + timedelta(minutes=interval_mins)).isoformat()
            update_system_status('twitter_scraper_status', {
                'next_run_at': next_run_iso,
                'interval_mins': interval_mins,
                'is_running': False, 
                'current_activity': 'Monitor Idle - All KOLs up to date'
            }, user_id=user_id)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Initial next_run_at set for {len(users)} users.")
    except Exception as e:
        print(f"⚠️ Error in update_next_run_at: {e}")

async def sync_scheduler_status(scheduler):
    while True:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT DISTINCT k.user_id, COALESCE(uc.scrape_interval_mins, %s) AS interval_mins
                FROM kols k
                JOIN user_configs uc ON k.user_id = uc.user_id
                WHERE k.status = 'active'
            """, (SCRAPE_INTERVAL,))
            users = [(str(r['user_id']), int(r['interval_mins'])) for r in cur.fetchall()]

            now = datetime.now(timezone.utc)
            for user_id, interval_mins in users:
                cur.execute("SELECT value FROM system_status WHERE key = %s", (make_status_key(user_id),))
                row = cur.fetchone()
                status = row['value'] if row else {}
                next_run_at = status.get('next_run_at')

                updates = {'interval_mins': interval_mins}
                if not next_run_at:
                    updates['next_run_at'] = (now + timedelta(minutes=interval_mins)).isoformat()

                update_system_status('twitter_scraper_status', updates, user_id=user_id)
            conn.close()
        except Exception as e:
            print(f"⚠️ Status sync error: {e}")
        await asyncio.sleep(30) # Update every 30s

async def main():
    scheduler = AsyncIOScheduler()

    # Handle Scraper Toggle
    enabled = os.getenv("SCRAPER_ENABLED", "true").lower() == "true"
    if enabled:
        # Scraper poller runs frequently and self-selects due users based on their configured intervals
        scheduler.add_job(run_twitter_scraper, 'interval', seconds=15, id='twitter_scraper')
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
