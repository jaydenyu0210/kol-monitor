"""
KOL Monitor Pro — FastAPI Backend (Cloud Edition)
Secured with Supabase JWT auth, connected via connection pool.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import httpx
from fastapi import FastAPI, Depends, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import API_PORT, FRONTEND_URL
from db import get_db, release_db
from config import SCRAPE_INTERVAL
from auth import get_current_user

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

app = FastAPI(title="KOL Monitor Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "https://kol-monitor-two.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Health Check ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ---------- Database Initialization & Migration ----------

def init_db():
    """Ensure required tables exist and schema is correct for Supabase UUIDs."""
    db = get_db()
    try:
        cur = db.cursor()
        # Ensure user_configs exists (migrated from legacy users table logic)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id TEXT PRIMARY KEY,
                discord_webhook_posts TEXT,
                discord_webhook_interactions TEXT,
                discord_webhook_heatmap TEXT,
                discord_webhook_following TEXT,
                discord_webhook_followers TEXT,
                twitter_auth_token TEXT,
                twitter_ct0 TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Ensure kols.user_id is TEXT to support Supabase UUIDs
        cur.execute("""
            DO $$ 
            BEGIN 
                IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='kols' AND column_name='user_id' AND data_type='integer') THEN
                    ALTER TABLE kols ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT;
                END IF;
            END $$;
        """)
        db.commit()
        print("✅ Database schema initialized correctly.")
    except Exception as e:
        print(f"⚠️ Error initializing database: {e}")
    finally:
        release_db(db)

def claim_legacy_data(user_id: str):
    """If this is a new Supabase user, check if there's legacy data to claim."""
    db = get_db()
    try:
        cur = db.cursor()
        # Check if user already has KOLs
        cur.execute("SELECT COUNT(*) FROM kols WHERE user_id = %s", (user_id,))
        count = cur.fetchone()[0]
        
        if count == 0:
            # Check if there are legacy KOLs (user_id = '1' or 'admin')
            cur.execute("SELECT COUNT(*) FROM kols WHERE user_id IN ('1', 'admin')")
            legacy_count = cur.fetchone()[0]
            
            if legacy_count > 0:
                print(f"📦 Found {legacy_count} legacy KOLs. Claiming for user {user_id}...")
                cur.execute("UPDATE kols SET user_id = %s WHERE user_id IN ('1', 'admin')", (user_id,))
                
                # Also claim legacy settings if any
                cur.execute("SELECT COUNT(*) FROM user_configs WHERE user_id = %s", (user_id,))
                if cur.fetchone()[0] == 0:
                    cur.execute("""
                        INSERT INTO user_configs (user_id, discord_webhook_posts, discord_webhook_interactions, discord_webhook_heatmap, twitter_auth_token, twitter_ct0)
                        SELECT %s, discord_webhook_posts, discord_webhook_interactions, discord_webhook_heatmap, twitter_auth_token, twitter_ct0
                        FROM user_configs WHERE user_id IN ('1', 'admin')
                        ON CONFLICT DO NOTHING
                    """, (user_id,))
                
                db.commit()
                return True
        return False
    except Exception as e:
        print(f"⚠️ Error claiming legacy data: {e}")
        return False
    finally:
        release_db(db)

# Initialize on startup
init_db()


# ---------- Pydantic Models ----------

class KolCreate(BaseModel):
    name: str
    org: Optional[str] = None
    category: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    notes: Optional[str] = None
    dm_text: Optional[str] = None
    dm_day: Optional[str] = None
    dm_time: Optional[str] = None


class KolUpdate(BaseModel):
    name: Optional[str] = None
    org: Optional[str] = None
    category: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    dm_text: Optional[str] = None
    dm_day: Optional[str] = None
    dm_time: Optional[str] = None


class WebhookSave(BaseModel):
    channel: str
    webhook_url: str


class CookieSave(BaseModel):
    auth_token: str
    ct0: str


class UserConfigUpdate(BaseModel):
    discord_webhook_posts: Optional[str] = None
    discord_webhook_interactions: Optional[str] = None
    discord_webhook_heatmap: Optional[str] = None
    discord_webhook_following: Optional[str] = None
    discord_webhook_followers: Optional[str] = None


# ---------- Status Sync Helper ----------

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
        
        db = get_db()
        try:
            cur = db.cursor()
            cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
            row = cur.fetchone()
            status = row[0] if row else {}
            status.update(value_updates)
            cur.execute("""
                INSERT INTO system_status (key, value, updated_at, user_id)
                VALUES (%s, %s, NOW(), %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW(), user_id = EXCLUDED.user_id
            """, (key, json.dumps(status), user_id))
            db.commit()
        finally:
            release_db(db)
    except Exception as e:
        print(f"⚠️ Error updating system_status ({key}): {e}")


# ---------- KOL Endpoints ----------

@app.get("/api/kols")
def list_kols(status: str = "active", user_id: str = Depends(get_current_user)):
    # Auto-claim if first time
    claim_legacy_data(user_id)
    
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT k.* FROM kols k
            WHERE k.user_id = %s AND k.status = %s
            ORDER BY k.created_at DESC
        """, (user_id, status))
        kols = cur.fetchall()
        
        # Auto-seed if 0 active KOLs found
        if not kols and status == "active":
            print(f"🌱 [SEED] Auto-seeding {len(DEFAULT_KOLS)} default KOLs for {user_id}")
            for handle in DEFAULT_KOLS:
                twitter_url = f"https://x.com/{handle}"
                cur.execute(
                    "INSERT INTO kols (user_id, name, twitter_url, status) VALUES (%s, %s, %s, 'active')",
                    (user_id, handle, twitter_url)
                )
            db.commit()
            # Fetch again after seeding
            cur.execute("""
                SELECT k.* FROM kols k
                WHERE k.user_id = %s AND k.status = %s
                ORDER BY k.created_at DESC
            """, (user_id, status))
            kols = cur.fetchall()

        return {"kols": kols}
    finally:
        release_db(db)


@app.post("/api/kols")
def create_kol(kol: KolCreate, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("""
            INSERT INTO kols (name, org, category, linkedin_url, twitter_url, notes, user_id, dm_text, dm_day, dm_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (kol.name, kol.org, kol.category, kol.linkedin_url,
              kol.twitter_url, kol.notes, user_id,
              kol.dm_text, kol.dm_day, kol.dm_time))
        kol_id = cur.fetchone()[0]
        db.commit()
        return {"id": kol_id, "message": "KOL created"}
    finally:
        release_db(db)


@app.put("/api/kols/{kol_id}")
def update_kol(kol_id: int, kol: KolUpdate, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor()
        fields = []
        values = []
        for field, value in kol.dict(exclude_unset=True).items():
            fields.append(f"{field} = %s")
            values.append(value)
        if not fields:
            raise HTTPException(400, "No fields to update")
        values.extend([kol_id, user_id])
        cur.execute(
            f"UPDATE kols SET {', '.join(fields)}, updated_at=NOW() WHERE id=%s AND user_id=%s",
            values
        )
        db.commit()
        return {"message": "KOL updated"}
    finally:
        release_db(db)


@app.delete("/api/kols/all")
def delete_all_kols(user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor()
        # Delete child records first
        cur.execute("""
            DELETE FROM dm_logs WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s);
            DELETE FROM kol_metrics WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s);
            DELETE FROM twitter_post_replies WHERE post_id IN (
                SELECT tp.id FROM twitter_posts tp JOIN kols k ON tp.kol_id=k.id WHERE k.user_id=%s
            );
            DELETE FROM twitter_post_reposts WHERE post_id IN (
                SELECT tp.id FROM twitter_posts tp JOIN kols k ON tp.kol_id=k.id WHERE k.user_id=%s
            );
            DELETE FROM twitter_posts WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s);
            
            -- Delete the KOLs themselves
            DELETE FROM kols WHERE user_id=%s;
        """, (user_id, user_id, user_id, user_id, user_id, user_id))
        db.commit()
        return {"message": "All KOLs and their historical data deleted"}
    finally:
        release_db(db)


@app.delete("/api/kols/{kol_id}")
def delete_kol(kol_id: int, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("DELETE FROM kols WHERE id=%s AND user_id=%s", (kol_id, user_id))
        db.commit()
        return {"message": "KOL deleted"}
    finally:
        release_db(db)


# ---------- Posts Endpoints ----------

@app.get("/api/twitter_posts")
def list_twitter_posts(
    kol_id: Optional[int] = None,
    days: int = 30,
    limit: int = 100,
    user_id: str = Depends(get_current_user)
):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        since = datetime.utcnow() - timedelta(days=days)
        if kol_id:
            cur.execute("""
                SELECT tp.*, k.name as kol_name FROM twitter_posts tp
                JOIN kols k ON tp.kol_id = k.id
                WHERE k.user_id = %s AND tp.kol_id = %s AND (tp.posted_at > %s OR (tp.posted_at IS NULL AND tp.captured_at > %s))
                ORDER BY tp.posted_at DESC, tp.captured_at DESC LIMIT %s
            """, (user_id, kol_id, since, since, limit))
        else:
            cur.execute("""
                SELECT tp.*, k.name as kol_name FROM twitter_posts tp
                JOIN kols k ON tp.kol_id = k.id
                WHERE k.user_id = %s AND (tp.posted_at > %s OR (tp.posted_at IS NULL AND tp.captured_at > %s))
                ORDER BY tp.posted_at DESC, tp.captured_at DESC LIMIT %s
            """, (user_id, since, since, limit))
        return {"posts": cur.fetchall()}
    finally:
        release_db(db)


# ---------- Metrics Endpoints ----------

@app.get("/api/metrics")
def list_metrics(
    kol_id: Optional[int] = None,
    days: int = 30,
    user_id: str = Depends(get_current_user)
):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        since = datetime.utcnow() - timedelta(days=days)
        if kol_id:
            cur.execute("""
                SELECT m.*, k.name as kol_name FROM kol_metrics m
                JOIN kols k ON m.kol_id = k.id
                WHERE k.user_id = %s AND m.kol_id = %s AND m.captured_at > %s
                ORDER BY m.captured_at DESC
            """, (user_id, kol_id, since))
        else:
            cur.execute("""
                SELECT m.*, k.name as kol_name FROM kol_metrics m
                JOIN kols k ON m.kol_id = k.id
                WHERE k.user_id = %s AND m.captured_at > %s
                ORDER BY m.captured_at DESC
            """, (user_id, since))
        return {"metrics": cur.fetchall()}
    finally:
        release_db(db)


from config import SCRAPE_INTERVAL

@app.get("/api/config")
def get_backend_config(user_id: str = Depends(get_current_user)):
    return {
        "scrape_interval": SCRAPE_INTERVAL,
        "environment": os.getenv("ENVIRONMENT_NAME", "Production"),
        "scraper_enabled": os.getenv("SCRAPER_ENABLED", "true").lower() == "true"
    }


@app.get("/api/scrape_status")
def get_scrape_status(user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Total active KOLs
        cur.execute("SELECT COUNT(*) as count FROM kols WHERE user_id=%s AND status='active'", (user_id,))
        total_kols = cur.fetchone()['count']
        
        # Get status from system_status (scheduler/manual sync)
        cur.execute("SELECT value FROM system_status WHERE key = %s", (f'twitter_scraper_status_{user_id}',))
        status_row = cur.fetchone()
        status_val = status_row['value'] if status_row and status_row['value'] else {}
        
        last_start_at = status_val.get('last_start_at')
        is_running_db = status_val.get('is_running', False)
        current_activity = status_val.get('current_activity', 'System Idle')
        next_run_at = status_val.get('next_run_at')

        # Calculate progress anchored to the last scrape start
        if last_start_at:
            # Count KOLs updated since the latest round started
            cur.execute("""
                SELECT name FROM kols 
                WHERE user_id=%s AND status='active' AND updated_at >= %s
                ORDER BY updated_at DESC
            """, (user_id, last_start_at))
            scraped_rows = cur.fetchall()
        else:
            scraped_rows = []
        
        scraped_kols = len(scraped_rows)
        scraped_names = [r['name'] for r in scraped_rows]
        
        # Get absolute last updated time across all active KOLs OR actual post capture
        cur.execute("""
            SELECT GREATEST(
                (SELECT MAX(updated_at) FROM kols WHERE user_id=%s AND status='active'),
                (SELECT MAX(tp.captured_at) FROM twitter_posts tp JOIN kols k ON tp.kol_id = k.id WHERE k.user_id=%s)
            ) as last_updated
        """, (user_id, user_id))
        max_row = cur.fetchone()
        last_updated = max_row['last_updated'].isoformat() if max_row and max_row['last_updated'] else None
        
        # Get status from system_status (scheduler/manual sync)
        cur.execute("SELECT value FROM system_status WHERE key = %s", (f'twitter_scraper_status_{user_id}',))
        status_row = cur.fetchone()
        status_val = status_row['value'] if status_row and status_row['value'] else {}
        
        next_run_at = status_val.get('next_run_at')
        is_running_db = status_val.get('is_running', False)
        current_activity = status_val.get('current_activity', 'System Idle')
        
        # Calculate relative seconds remaining to avoid client clock skew
        next_run_seconds = 0
        if next_run_at:
            try:
                nr_dt = datetime.fromisoformat(next_run_at)
                diff = (nr_dt - datetime.now(timezone.utc)).total_seconds()
                next_run_seconds = max(0, int(diff))
            except: pass

        return {
            "total": total_kols,
            "scraped": scraped_kols,
            "is_running": is_running_db,
            "last_updated": status_val.get('last_start_at'),
            "next_run_seconds": next_run_seconds,
            "current_activity": status_val.get('current_activity'),
            "instance": status_val.get('instance', 'Unknown')
        }
    finally:
        release_db(db)


# ---------- Stats Endpoint ----------

@app.get("/api/stats")
def get_stats(user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Total active KOLs
        cur.execute("SELECT COUNT(*) as count FROM kols WHERE user_id=%s AND status='active'", (user_id,))
        total_kols = cur.fetchone()["count"]

        # 2. Total Posts
        cur.execute("SELECT COUNT(*) as count FROM twitter_posts tp JOIN kols k ON tp.kol_id = k.id WHERE k.user_id = %s", (user_id,))
        total_posts = cur.fetchone()["count"]

        # 3. Posts in last 24h
        since_24h = datetime.utcnow() - timedelta(hours=24)
        cur.execute("""
            SELECT COUNT(*) as count FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s AND tp.captured_at > %s
        """, (user_id, since_24h))
        posts_today = cur.fetchone()["count"]

        # 4. Interactions today (sum of counts for posts from last 24h)
        cur.execute("""
            SELECT COALESCE(SUM(likes + reposts + comments), 0) as count 
            FROM twitter_posts tp JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s AND tp.captured_at > %s
        """, (user_id, since_24h))
        interactions_today = int(cur.fetchone()["count"])

        # 5. Connection changes (followers + following deltas)
        cur.execute("""
            SELECT COALESCE(SUM(m2.followers_count - m1.followers_count), 0) as f_delta,
                   COALESCE(SUM(m2.following_count - m1.following_count), 0) as fg_delta
            FROM (
                SELECT DISTINCT ON (kol_id) kol_id, followers_count, following_count
                FROM kol_metrics WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s)
                ORDER BY kol_id, captured_at DESC
            ) m2
            JOIN (
                SELECT DISTINCT ON (kol_id) kol_id, followers_count, following_count
                FROM kol_metrics WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s)
                ORDER BY kol_id, captured_at DESC OFFSET 1
            ) m1 ON m2.kol_id = m1.kol_id
        """, (user_id, user_id))
        row = cur.fetchone()
        connection_changes_today = abs(row["f_delta"]) + abs(row["fg_delta"])

        return {
            "total_kols": total_kols,
            "posts_today": posts_today,
            "interactions_today": interactions_today,
            "connection_changes_today": connection_changes_today,
            "total_posts": total_posts
        }
    finally:
        release_db(db)


# ---------- Settings / User Config Endpoints ----------

@app.get("/api/settings")
def get_settings(user_id: str = Depends(get_current_user)):
    # Auto-claim if first time
    claim_legacy_data(user_id)
    
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM user_configs WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return {"user_id": user_id, "has_cookies": False}
        row["has_cookies"] = bool(row.get("twitter_auth_token"))
        return row
    finally:
        release_db(db)


@app.post("/api/settings/webhooks")
def save_webhooks(data: UserConfigUpdate, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("""
            INSERT INTO user_configs (user_id, discord_webhook_posts, discord_webhook_interactions,
                discord_webhook_heatmap, discord_webhook_following, discord_webhook_followers)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                discord_webhook_posts = COALESCE(EXCLUDED.discord_webhook_posts, user_configs.discord_webhook_posts),
                discord_webhook_interactions = COALESCE(EXCLUDED.discord_webhook_interactions, user_configs.discord_webhook_interactions),
                discord_webhook_heatmap = COALESCE(EXCLUDED.discord_webhook_heatmap, user_configs.discord_webhook_heatmap),
                discord_webhook_following = COALESCE(EXCLUDED.discord_webhook_following, user_configs.discord_webhook_following),
                discord_webhook_followers = COALESCE(EXCLUDED.discord_webhook_followers, user_configs.discord_webhook_followers),
                updated_at = now()
        """, (user_id, data.discord_webhook_posts, data.discord_webhook_interactions,
              data.discord_webhook_heatmap, data.discord_webhook_following, data.discord_webhook_followers))
        db.commit()
        return {"message": "Webhooks saved"}
    finally:
        release_db(db)


@app.post("/api/settings/webhook/test")
async def test_webhook(data: WebhookSave, user_id: str = Depends(get_current_user)):
    """Dry-run test: sends a confirmation message to the provided webhook URL."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(data.webhook_url, json={
                "content": f"✅ **KOL Monitor Pro**: Webhook for `{data.channel}` connected successfully!"
            })
            if res.status_code not in (200, 204):
                raise HTTPException(400, f"Webhook returned status {res.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(400, f"Could not reach webhook: {e}")
    return {"message": f"Test message sent to {data.channel} webhook"}


class DiscordPushRequest(BaseModel):
    channel: str  # "posts", "following", "followers", "heatmap", "interactions", or "all"


@app.post("/api/discord/push")
async def trigger_discord_push(data: DiscordPushRequest, user_id: str = Depends(get_current_user)):
    """Manually trigger Discord push for a specific channel or all channels."""
    from discord_push import (
        build_post_embeds, build_following_embeds, build_follower_embeds,
        build_heatmap_embeds, build_interaction_embeds, send_embeds
    )

    # Get user's webhooks
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT discord_webhook_posts, discord_webhook_interactions,
                   discord_webhook_heatmap, discord_webhook_following,
                   discord_webhook_followers
            FROM user_configs WHERE user_id = %s
        """, (user_id,))
        config = cur.fetchone()
    finally:
        release_db(db)

    if not config:
        raise HTTPException(404, "No webhook configuration found")

    channel_map = {
        "posts": ("discord_webhook_posts", build_post_embeds),
        "following": ("discord_webhook_following", build_following_embeds),
        "followers": ("discord_webhook_followers", build_follower_embeds),
        "heatmap": ("discord_webhook_heatmap", build_heatmap_embeds),
        "interactions": ("discord_webhook_interactions", build_interaction_embeds),
    }

    channels_to_push = list(channel_map.keys()) if data.channel == "all" else [data.channel]
    sent = 0
    no_data = 0

    for ch in channels_to_push:
        if ch not in channel_map:
            continue
        webhook_key, build_fn = channel_map[ch]
        webhook_url = config.get(webhook_key)
        if not webhook_url:
            continue

        try:
            if ch == "heatmap":
                embeds = build_fn(user_id)
            else:
                embeds = build_fn(user_id, interval_mins=1440)  # Look back 24h for manual trigger
            
            if embeds:
                await send_embeds(webhook_url, embeds)
                sent += 1
            else:
                # Manual trigger also sends "No data" message to Discord as requested
                from discord_push import send_discord_async
                channel_display = ch.capitalize()
                pass
                no_data += 1
        except Exception as e:
            print(f"⚠️ Error pushing {ch}: {e}")

    msg = f"Pushed {sent} channel(s) to Discord."
    if no_data:
        msg += f" {no_data} channel(s) had no new data."
    return {"message": msg}


@app.post("/api/settings/cookies")
def save_cookies(data: CookieSave, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("""
            INSERT INTO user_configs (user_id, twitter_auth_token, twitter_ct0)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                twitter_auth_token = %s, twitter_ct0 = %s, updated_at = now()
        """, (user_id, data.auth_token, data.ct0, data.auth_token, data.ct0))
        db.commit()
        return {"message": "X cookies saved"}
    finally:
        release_db(db)


@app.get("/api/overview_feed")
def get_overview_feed(user_id: str = Depends(get_current_user)):
    def load_feed(name):
        path = f"/app/feed_{name}_{user_id}.json"
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading feed {name}: {e}")
        return []

    return {
        "recent_posts": load_feed("posts"),
        "hot_posts": load_feed("heatmap"),
        "interactions": load_feed("interactions"),
        "following_changes": load_feed("following"),
        "follower_changes": load_feed("followers")
    }


@app.get("/api/discord_posts_history")
def get_discord_posts_history(
    date: str = None, 
    sort: str = "recent",
    tz: str = "UTC",
    minutes: Optional[int] = None,
    days: Optional[int] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Returns posts captured for this user. 
    If minutes is provided, filters by discovery time in the last X minutes.
    If days is provided, filters by discovery time in the last X days.
    Otherwise, filters by discovery date in a specific timezone.
    """
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        sort_dir = "DESC" if sort == "recent" else "ASC"

        if minutes is not None:
            # Filter by minutes relative to NOW (UTC)
            since = datetime.utcnow() - timedelta(minutes=minutes)
            cur.execute(f"""
                SELECT tp.*, k.name as kol 
                FROM twitter_posts tp
                JOIN kols k ON tp.kol_id = k.id
                WHERE k.user_id = %s 
                  AND tp.posted_at >= %s
                ORDER BY tp.posted_at DESC
            """, (user_id, since))
        elif days is not None:
             # Filter by days relative to NOW (UTC)
            since = datetime.utcnow() - timedelta(days=days)
            cur.execute(f"""
                SELECT tp.*, k.name as kol, k.name as kol_name
                FROM twitter_posts tp
                JOIN kols k ON tp.kol_id = k.id
                WHERE k.user_id = %s 
                  AND tp.posted_at >= %s
                ORDER BY tp.posted_at DESC
            """, (user_id, since))
            rows = cur.fetchall()
            return { "posts": rows }
        else:
            # Default to last 7 days for general heatmap/summary
            since = datetime.utcnow() - timedelta(days=7)
            cur.execute(f"""
                SELECT tp.*, k.name as kol, k.name as kol_name
                FROM twitter_posts tp
                JOIN kols k ON tp.kol_id = k.id
                WHERE k.user_id = %s 
                  AND tp.posted_at >= %s
                ORDER BY tp.posted_at {sort_dir}
            """, (user_id, since))
        
        return { "posts": cur.fetchall() }
    finally:
        release_db(db)


def run_manual_scrape_task(user_id):
    """Background task to run scraper and discord push for a specific user"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Manual scrape task started in background", flush=True)
    
    # 0. Set is_running flag
    db = get_db()
    try:
        cur = db.cursor()
        update_system_status('twitter_scraper_status', {
            'is_running': True,
            'last_start_at': datetime.now(timezone.utc).isoformat(),
            'current_activity': 'Starting manual scrape round...'
        }, user_id=user_id)
    except Exception as e:
        print(f"⚠️ Error setting manual is_running: {e}")
    finally:
        release_db(db)

    try:
        # 1. Run Scraper
        # Ensure we use an absolute path that works in Docker and get immediate output
        scraper_path = os.path.join(os.getcwd(), "twitter_scraper.py")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏃 Executing scraper for user {user_id}: {scraper_path}", flush=True)
        
        # Override LIMIT_TO_USER_ID for this specific run to ensure we scrape the requester
        env = os.environ.copy()
        env["LIMIT_TO_USER_ID"] = user_id
        
        subprocess.run([sys.executable, "-u", scraper_path], env=env, timeout=3600, check=True)
        # 2. Run Discord Pushes
        for job in ["posts", "following", "followers", "heatmap", "interactions"]:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Manual Pushing {job.upper()} to Discord...")
            subprocess.run([sys.executable, "/app/discord_push.py", job], timeout=120)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Manual scrape task complete.")
    except Exception as e:
        print(f"❌ Manual scrape task error: {e}")
    finally:
        # Clear is_running flag and reset activity
        update_system_status('twitter_scraper_status', {
            'is_running': False,
            'current_activity': 'Monitor Idle - All KOLs up to date'
        }, user_id=user_id)


@app.post("/api/trigger_manual_scrape")
async def trigger_manual_scrape(background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user)):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📥 API: Received request to trigger manual scrape for user {user_id}", flush=True)
    background_tasks.add_task(run_manual_scrape_task, user_id)
    return {"message": "Manual scrape triggered in background"}


# ---------- DM Logs ----------

@app.get("/api/dm_logs")
def get_dm_logs(user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT l.*, k.name as kol_name
            FROM dm_logs l
            JOIN kols k ON l.kol_id = k.id
            WHERE k.user_id = %s
            ORDER BY l.sent_at DESC
            LIMIT 50
        """, (user_id,))
        return {"logs": cur.fetchall()}
    finally:
        release_db(db)


# ---------- Post Replies/Reposts ----------

@app.get("/api/post_replies")
def get_post_replies(post_id: int, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT r.username, r.captured_at FROM twitter_post_replies r
            JOIN twitter_posts tp ON r.post_id = tp.id
            JOIN kols k ON tp.kol_id = k.id
            WHERE r.post_id = %s AND k.user_id = %s
            ORDER BY r.captured_at DESC
        """, (post_id, user_id))
        return {"replies": cur.fetchall()}
    finally:
        release_db(db)


@app.get("/api/post_reposts")
def get_post_reposts(post_id: int, user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT r.username, r.captured_at FROM twitter_post_reposts r
            JOIN twitter_posts tp ON r.post_id = tp.id
            JOIN kols k ON tp.kol_id = k.id
            WHERE r.post_id = %s AND k.user_id = %s
            ORDER BY r.captured_at DESC
        """, (post_id, user_id))
        return {"reposts": cur.fetchall()}
    finally:
        release_db(db)


# ---------- Main ----------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
