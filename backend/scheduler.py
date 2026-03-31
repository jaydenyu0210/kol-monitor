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

def make_newposts_status_key(user_id=None):
    env_suffix = os.getenv("ENVIRONMENT_NAME", "Local").replace(" ", "_").lower()
    base = "twitter_newposts_status"
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

NEWPOSTS_INTERVAL = 30  # New posts scan runs every 30 minutes

def run_newposts_scraper():
    """Scheduled job: quick scan for new posts (last 30 minutes) across all users."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ℹ️ [NEW POSTS] No active users with credentials. Skipping.")
            return
    except Exception as e:
        print(f"⚠️ New posts scheduler error: {e}")
        return

    # Check which users are not already running a new posts scan
    due_users = []
    now = datetime.now(timezone.utc)
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for user_id in users:
            key = make_newposts_status_key(user_id)
            cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
            row = cur.fetchone()
            status = row['value'] if row else {}

            if status.get('is_running', False):
                continue  # Already running

            # Check if enough time has passed since last scan
            next_run_at = status.get('next_run_at')
            if next_run_at:
                try:
                    next_run_dt = datetime.fromisoformat(next_run_at)
                    if now < next_run_dt - timedelta(seconds=2):
                        continue  # Not due yet
                except:
                    pass

            due_users.append(user_id)
            update_system_status(key, {
                'is_running': True,
                'last_start_at': now.isoformat(),
                'current_activity': 'Starting new posts scan...',
                'next_run_at': None
            }, user_id=user_id)
        conn.close()
    except Exception as e:
        print(f"⚠️ New posts status evaluation error: {e}")
        return

    if not due_users:
        return

    try:
        env = os.environ.copy()
        env["LIMIT_TO_USER_IDS"] = ",".join(due_users)
        process = subprocess.Popen(
            [sys.executable, "-u", "/app/twitter_scraper.py", "newposts"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        for line in process.stdout:
            print(f"[NEW POSTS] {line.strip()}", flush=True)
        process.wait(timeout=1800)
    except Exception as e:
        print(f"❌ [NEW POSTS] Error: {e}")
    finally:
        # Discord push is now handled directly inside twitter_scraper.py after each user's scan

        # Set next run time
        try:
            now_done = datetime.now(timezone.utc)
            for user_id in due_users:
                key = make_newposts_status_key(user_id)
                next_run = now_done + timedelta(minutes=NEWPOSTS_INTERVAL)
                update_system_status(key, {
                    'is_running': False,
                    'next_run_at': next_run.isoformat(),
                    'current_activity': f'Idle - Next scan in {NEWPOSTS_INTERVAL}m'
                }, user_id=user_id)
                print(f"[{now_done.strftime('%H:%M:%S')}] ✅ New posts scan done for user {user_id}. Next at {next_run.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️ New posts status completion error: {e}")

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
    """Safety sync on startup: reset heatmap running state, initialize new posts schedule."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🕒 Performing startup schedule sync...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT DISTINCT k.user_id
            FROM kols k
            JOIN user_configs uc ON k.user_id = uc.user_id
            WHERE k.status = 'active'
        """)
        users = [str(r['user_id']) for r in cur.fetchall()]
        conn.close()

        now = datetime.now(timezone.utc)
        for user_id in users:
            # Reset heatmap scrape state on restart (manual-only, no auto timer)
            update_system_status('twitter_scraper_status', {
                'is_running': False,
                'current_activity': 'Heatmap scrape: Manual only',
                'heatmap_finished_at': None  # Clear cooldown on restart
            }, user_id=user_id)

            # Initialize new posts scrape schedule
            newposts_key = make_newposts_status_key(user_id)
            next_run_iso = (now + timedelta(minutes=1)).isoformat()  # First run 1 min after startup
            update_system_status(newposts_key, {
                'next_run_at': next_run_iso,
                'is_running': False,
                'current_activity': f'Idle - Next scan in 1m'
            }, user_id=user_id)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Startup sync done for {len(users)} users (heatmap=manual, newposts=30m cycle).")
    except Exception as e:
        print(f"⚠️ Error in update_next_run_at: {e}")

async def sync_scheduler_status(scheduler):
    while True:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT DISTINCT k.user_id
                FROM kols k
                JOIN user_configs uc ON k.user_id = uc.user_id
                WHERE k.status = 'active'
            """)
            users = [str(r['user_id']) for r in cur.fetchall()]

            now = datetime.now(timezone.utc)
            for user_id in users:
                # Sync new posts schedule
                newposts_key = make_newposts_status_key(user_id)
                cur.execute("SELECT value FROM system_status WHERE key = %s", (newposts_key,))
                row = cur.fetchone()
                status = row['value'] if row else {}
                if not status.get('next_run_at') and not status.get('is_running'):
                    update_system_status(newposts_key, {
                        'next_run_at': (now + timedelta(minutes=NEWPOSTS_INTERVAL)).isoformat()
                    }, user_id=user_id)
            conn.close()
        except Exception as e:
            print(f"⚠️ Status sync error: {e}")
        await asyncio.sleep(30)

async def main():
    scheduler = AsyncIOScheduler()

    # Handle Scraper Toggle
    enabled = os.getenv("SCRAPER_ENABLED", "true").lower() == "true"
    if enabled:
        # New posts quick scan polls every 15s and self-selects due users (30-min cycle)
        scheduler.add_job(run_newposts_scraper, 'interval', seconds=15, id='newposts_scraper', max_instances=1)
        # DM Scheduler runs every SCRAPE_INTERVAL minutes
        scheduler.add_job(run_dm_scheduler, 'interval', minutes=SCRAPE_INTERVAL, id='dm_scheduler_job')
        scheduler.start()
        print(f"📅 KOL Monitor Scheduler Started [Heatmap=Manual, NewPosts={NEWPOSTS_INTERVAL}m cycle] [Env: {os.getenv('ENVIRONMENT_NAME', 'Local')}]")
    else:
        print(f"⏸️  KOL Monitor Scheduler DISABLED via SCRAPER_ENABLED=false [Env: {os.getenv('ENVIRONMENT_NAME', 'Local')}]")

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
