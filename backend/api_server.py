"""
KOL Monitor Pro — FastAPI Backend (Cloud Edition)
Secured with Supabase JWT auth, connected via connection pool.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
import httpx
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import API_PORT, FRONTEND_URL
from db import get_db, release_db
from auth import get_current_user

app = FastAPI(title="KOL Monitor Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Health Check ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


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


# ---------- KOL Endpoints ----------

@app.get("/api/kols")
def list_kols(status: str = "active", user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
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
            DELETE FROM kols WHERE user_id=%s;
        """, (user_id, user_id, user_id, user_id, user_id, user_id))
        db.commit()
        return {"message": "All KOLs deleted"}
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
                WHERE k.user_id = %s AND tp.kol_id = %s AND tp.captured_at > %s
                ORDER BY tp.captured_at DESC LIMIT %s
            """, (user_id, kol_id, since, limit))
        else:
            cur.execute("""
                SELECT tp.*, k.name as kol_name FROM twitter_posts tp
                JOIN kols k ON tp.kol_id = k.id
                WHERE k.user_id = %s AND tp.captured_at > %s
                ORDER BY tp.captured_at DESC LIMIT %s
            """, (user_id, since, limit))
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


# ---------- Stats Endpoint ----------

@app.get("/api/stats")
def get_stats(user_id: str = Depends(get_current_user)):
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Total active KOLs
        cur.execute("SELECT COUNT(*) as count FROM kols WHERE user_id=%s AND status='active'", (user_id,))
        total_kols = cur.fetchone()["count"]

        # Posts in last 24h
        since_24h = datetime.utcnow() - timedelta(hours=24)
        cur.execute("""
            SELECT COUNT(*) as count FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s AND tp.captured_at > %s
        """, (user_id, since_24h))
        recent_posts = cur.fetchone()["count"]

        # Follower delta (latest vs previous snapshot)
        cur.execute("""
            SELECT COALESCE(SUM(m2.followers_count - m1.followers_count), 0) as delta
            FROM (
                SELECT DISTINCT ON (kol_id) kol_id, followers_count
                FROM kol_metrics WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s)
                ORDER BY kol_id, captured_at DESC
            ) m2
            JOIN (
                SELECT DISTINCT ON (kol_id) kol_id, followers_count
                FROM kol_metrics WHERE kol_id IN (SELECT id FROM kols WHERE user_id=%s)
                ORDER BY kol_id, captured_at DESC OFFSET 1
            ) m1 ON m2.kol_id = m1.kol_id
        """, (user_id, user_id))
        row = cur.fetchone()
        follower_delta = row["delta"] if row else 0

        return {
            "total_kols": total_kols,
            "recent_posts": recent_posts,
            "follower_delta": follower_delta,
        }
    finally:
        release_db(db)


# ---------- Settings / User Config Endpoints ----------

@app.get("/api/settings")
def get_settings(user_id: str = Depends(get_current_user)):
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


@app.put("/api/settings/webhooks")
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
