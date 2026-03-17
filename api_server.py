"""
KOL Monitor API Server - FastAPI backend for dashboard + Telegram push
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config import DB_DSN, API_PORT

app = FastAPI(title="KOL Monitor Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    return conn

# ---------- Models ----------

class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class KolCreate(BaseModel):
    name: str
    org: Optional[str] = None
    category: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    notes: Optional[str] = None
    user_id: int = 1 # Default for transition

class KolUpdate(BaseModel):
    name: Optional[str] = None
    org: Optional[str] = None
    category: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

# ---------- Dashboard HTML ----------

@app.get("/test", response_class=HTMLResponse)
async def dashboard_test():
    html_path = os.path.join(os.path.dirname(__file__), "dashboard_test.html")
    with open(html_path, "r") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, "r") as f:
        return f.read()

# ---------- User/Auth Endpoints ----------

@app.post("/api/auth/register")
def register(user: UserCreate):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (%s, %s, %s) RETURNING id",
            (user.username, user.password, user.email) # In real SaaS, use bcrypt/hash!
        )
        user_id = cur.fetchone()[0]
        db.commit()
        return {"id": user_id, "message": "User registered"}
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    finally:
        db.close()

@app.post("/api/auth/login")
def login(user: UserLogin):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s AND password_hash = %s", (user.username, user.password))
    row = cur.fetchone()
    db.close()
    if row:
        return {"id": row['id'], "username": row['username'], "status": "success"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# ---------- KOL Endpoints ----------

@app.get("/api/kols")
def list_kols(user_id: int = 1, status: str = "active"):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT k.*, 
            (SELECT COUNT(*) FROM linkedin_posts WHERE kol_id=k.id) as post_count,
            (SELECT COUNT(*) FROM linkedin_interactions WHERE kol_id=k.id) as interaction_count,
            (SELECT followers_count FROM kol_metrics WHERE kol_id=k.id ORDER BY captured_at DESC LIMIT 1) as latest_followers,
            (SELECT connections_count FROM kol_metrics WHERE kol_id=k.id ORDER BY captured_at DESC LIMIT 1) as latest_connections
        FROM kols k
        WHERE k.status = %s AND k.user_id = %s
        ORDER BY k.id
    """, (status, user_id))
    rows = cur.fetchall()
    db.close()
    return {"kols": [dict(r) for r in rows]}

@app.post("/api/kols")
def create_kol(kol: KolCreate):
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO kols (name, org, category, linkedin_url, twitter_url, notes, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (kol.name, kol.org, kol.category, kol.linkedin_url, kol.twitter_url, kol.notes, kol.user_id))
    kol_id = cur.fetchone()[0]
    db.commit()
    db.close()
    return {"id": kol_id, "message": "KOL created"}

@app.put("/api/kols/{kol_id}")
def update_kol(kol_id: int, kol: KolUpdate):
    db = get_db()
    cur = db.cursor()
    fields = []
    values = []
    for field, value in kol.dict(exclude_unset=True).items():
        fields.append(f"{field} = %s")
        values.append(value)
    if not fields:
        raise HTTPException(400, "No fields to update")
    values.append(kol_id)
    cur.execute(f"UPDATE kols SET {', '.join(fields)}, updated_at=NOW() WHERE id=%s", values)
    db.commit()
    db.close()
    return {"message": "KOL updated"}

@app.delete("/api/kols/all")
def delete_all_kols(user_id: int):
    db = get_db()
    cur = db.cursor()
    # Delete posts and metrics first to avoid FK constraints if necessary, 
    # though most tables reference kols(id) and might need cleanup or ON DELETE CASCADE.
    # In this schema, linkedin_posts and others reference kols(id).
    cur.execute("DELETE FROM linkedin_posts WHERE kol_id IN (SELECT id FROM kols WHERE user_id = %s)", (user_id,))
    cur.execute("DELETE FROM twitter_posts WHERE kol_id IN (SELECT id FROM kols WHERE user_id = %s)", (user_id,))
    cur.execute("DELETE FROM kol_metrics WHERE kol_id IN (SELECT id FROM kols WHERE user_id = %s)", (user_id,))
    cur.execute("DELETE FROM linkedin_interactions WHERE kol_id IN (SELECT id FROM kols WHERE user_id = %s)", (user_id,))
    cur.execute("DELETE FROM linkedin_connections WHERE kol_id IN (SELECT id FROM kols WHERE user_id = %s)", (user_id,))
    cur.execute("DELETE FROM dm_logs WHERE kol_id IN (SELECT id FROM kols WHERE user_id = %s)", (user_id,))
    
    cur.execute("DELETE FROM kols WHERE user_id = %s", (user_id,))
    db.commit()
    db.close()
    return {"message": "All KOLs and related data deleted for user"}

@app.delete("/api/kols/{kol_id}")
def delete_kol(kol_id: int):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE kols SET status='inactive' WHERE id=%s", (kol_id,))
    db.commit()
    db.close()
    return {"message": "KOL deactivated"}

# ---------- Posts Endpoints ----------

@app.get("/api/posts")
def list_posts(user_id: int = 1, kol_id: Optional[int] = None, days: int = 7, limit: int = 50):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = datetime.now() - timedelta(days=days)
    
    if kol_id:
        cur.execute("""
            SELECT p.*, k.name as kol_name FROM linkedin_posts p
            JOIN kols k ON k.id = p.kol_id
            WHERE k.user_id = %s AND p.kol_id = %s AND p.captured_at >= %s
            ORDER BY p.captured_at DESC LIMIT %s
        """, (user_id, kol_id, since, limit))
    else:
        cur.execute("""
            SELECT p.*, k.name as kol_name FROM linkedin_posts p
            JOIN kols k ON k.id = p.kol_id
            WHERE k.user_id = %s AND p.captured_at >= %s
            ORDER BY p.captured_at DESC LIMIT %s
        """, (user_id, since, limit))
    
    rows = cur.fetchall()
    db.close()
    return {"posts": [dict(r) for r in rows]}


@app.get("/api/twitter_posts")
def list_twitter_posts(user_id: int = 1, kol_id: Optional[int] = None, days: int = 30, limit: int = 100):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = datetime.now() - timedelta(days=days)
    
    if kol_id:
        cur.execute("""
            SELECT p.*, k.name as kol_name FROM twitter_posts p
            JOIN kols k ON k.id = p.kol_id
            WHERE k.user_id = %s AND p.kol_id = %s AND p.posted_at >= %s
            ORDER BY p.posted_at ASC LIMIT %s
        """, (user_id, kol_id, since, limit))
    else:
        cur.execute("""
            SELECT p.*, k.name as kol_name FROM twitter_posts p
            JOIN kols k ON k.id = p.kol_id
            WHERE k.user_id = %s AND p.posted_at >= %s
            ORDER BY p.posted_at ASC LIMIT %s
        """, (user_id, since, limit))
    
    rows = cur.fetchall()
    db.close()
    return {"posts": [dict(r) for r in rows]}

# ---------- Interactions Endpoints ----------


@app.get("/api/interactions")
def list_interactions(user_id: int = 1, kol_id: Optional[int] = None, days: int = 7, limit: int = 50):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = datetime.now() - timedelta(days=days)
    
    if kol_id:
        cur.execute("""
            SELECT i.*, k.name as kol_name FROM linkedin_interactions i
            JOIN kols k ON k.id = i.kol_id
            WHERE k.user_id = %s AND i.kol_id = %s AND i.captured_at >= %s
            ORDER BY i.captured_at DESC LIMIT %s
        """, (user_id, kol_id, since, limit))
    else:
        cur.execute("""
            SELECT i.*, k.name as kol_name FROM linkedin_interactions i
            JOIN kols k ON k.id = i.kol_id
            WHERE k.user_id = %s AND i.captured_at >= %s
            ORDER BY i.captured_at DESC LIMIT %s
        """, (user_id, since, limit))
    
    rows = cur.fetchall()
    db.close()
    return {"interactions": [dict(r) for r in rows]}

# ---------- Metrics Endpoints ----------

@app.get("/api/metrics")
def list_metrics(user_id: int = 1, kol_id: Optional[int] = None, days: int = 30):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = datetime.now() - timedelta(days=days)
    
    if kol_id:
        cur.execute("""
            SELECT m.*, k.name as kol_name FROM kol_metrics m
            JOIN kols k ON k.id = m.kol_id
            WHERE k.user_id = %s AND m.kol_id = %s AND m.captured_at >= %s
            ORDER BY m.captured_at DESC
        """, (user_id, kol_id, since))
    else:
        cur.execute("""
            SELECT m.*, k.name as kol_name FROM kol_metrics m
            JOIN kols k ON k.id = m.kol_id
            WHERE k.user_id = %s AND m.captured_at >= %s
            ORDER BY m.captured_at DESC
        """, (user_id, since,))
    
    rows = cur.fetchall()
    db.close()
    return {"metrics": [dict(r) for r in rows]}

# ---------- Connections Endpoints ----------

@app.get("/api/connections")
def list_connections(user_id: int = 1, kol_id: Optional[int] = None, change_type: Optional[str] = None, days: int = 7, limit: int = 100):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = datetime.now() - timedelta(days=days)
    
    query = """
        SELECT c.*, k.name as kol_name FROM linkedin_connections c
        JOIN kols k ON k.id = c.kol_id
        WHERE k.user_id = %s AND c.detected_at >= %s
    """
    params = [user_id, since]
    
    if kol_id:
        query += " AND c.kol_id = %s"
        params.append(kol_id)
    if change_type:
        query += " AND c.change_type = %s"
        params.append(change_type)
    
    query += " ORDER BY c.detected_at DESC LIMIT %s"
    params.append(limit)
    
    cur.execute(query, params)
    rows = cur.fetchall()
    db.close()
    return {"connections": [dict(r) for r in rows]}

# ---------- Stats Endpoint ----------

@app.get("/api/stats")
def get_stats(user_id: int = 1):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    cur.execute("SELECT COUNT(*) as total FROM kols WHERE status='active' AND user_id=%s", (user_id,))
    total_kols = cur.fetchone()['total']
    
    cur.execute("""
        SELECT COUNT(*) as total FROM linkedin_posts p 
        JOIN kols k ON p.kol_id = k.id 
        WHERE k.user_id=%s AND p.captured_at >= %s
    """, (user_id, today))
    posts_today = cur.fetchone()['total']
    
    cur.execute("""
        SELECT COUNT(*) as total FROM linkedin_interactions i
        JOIN kols k ON i.kol_id = k.id
        WHERE k.user_id=%s AND i.captured_at >= %s
    """, (user_id, today))
    interactions_today = cur.fetchone()['total']
    
    cur.execute("""
        SELECT COUNT(*) as total FROM linkedin_connections c
        JOIN kols k ON c.kol_id = k.id
        WHERE k.user_id=%s AND c.change_type IN ('new','removed') AND c.detected_at >= %s
    """, (user_id, today))
    connection_changes_today = cur.fetchone()['total']
    
    cur.execute("""
        SELECT COUNT(*) as total FROM linkedin_posts p
        JOIN kols k ON p.kol_id = k.id
        WHERE k.user_id=%s
    """, (user_id,))
    total_posts = cur.fetchone()['total']
    
    cur.execute("""
        SELECT k.name, COUNT(p.id) as cnt FROM linkedin_posts p
        JOIN kols k ON k.id = p.kol_id
        WHERE k.user_id=%s AND p.captured_at >= %s
        GROUP BY k.name ORDER BY cnt DESC LIMIT 5
    """, (user_id, today - timedelta(days=7)))
    top_posters = [dict(r) for r in cur.fetchall()]
    
    db.close()
    return {
        "total_kols": total_kols,
        "posts_today": posts_today,
        "interactions_today": interactions_today,
        "connection_changes_today": connection_changes_today,
        "total_posts": total_posts,
        "top_posters": top_posters,
    }

class CookieUpdate(BaseModel):
    auth_token: str
    ct0: str
    user_id: int = 1

class UserUpdate(BaseModel):
    discord_webhook_posts: Optional[str] = None
    discord_webhook_interactions: Optional[str] = None
    discord_webhook_metrics: Optional[str] = None
    discord_webhook_heatmap: Optional[str] = None
    discord_webhook_following: Optional[str] = None
    discord_webhook_followers: Optional[str] = None

@app.put("/api/auth/profile")
def update_profile(user_id: int, data: UserUpdate):
    db = get_db()
    cur = db.cursor()
    fields = []
    values = []
    for field, value in data.dict(exclude_unset=True).items():
        fields.append(f"{field} = %s")
        values.append(value)
    if not fields:
        raise HTTPException(400, "No fields to update")
    values.append(user_id)
    cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=%s", values)
    db.commit()
    db.close()
    return {"status": "success", "message": "Profile updated"}

@app.get("/api/auth/profile")
def get_profile(user_id: int):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT username, email, discord_webhook_posts, discord_webhook_interactions, discord_webhook_metrics, discord_webhook_heatmap, discord_webhook_following, discord_webhook_followers FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    db.close()
    if row:
        # Check if cookies exist for this user
        creds_path = f"/data/.openclaw/workspace/kol-monitor/credentials/twitter_{user_id}.json"
        row['has_cookies'] = os.path.exists(creds_path)
        return row
    raise HTTPException(404, "User not found")

@app.post("/api/config/cookies")
def update_cookies(data: CookieUpdate):
    # In Multi-tenant mode, we store user-specific cookies in a credentials folder
    creds_dir = "/data/.openclaw/workspace/kol-monitor/credentials"
    os.makedirs(creds_dir, exist_ok=True)
    
    creds_path = os.path.join(creds_dir, f"twitter_{data.user_id}.json")
    with open(creds_path, "w") as f:
        json.dump({"auth_token": data.auth_token, "ct0": data.ct0}, f)
    
    return {"status": "success", "message": f"Cookies updated for User {data.user_id}."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)

@app.get("/api/post_replies")
def get_post_replies(post_id: int):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT username, captured_at FROM twitter_post_replies 
        WHERE post_id = %s ORDER BY captured_at DESC
    """, (post_id,))
    res = cur.fetchall()
    db.close()
    return {"replies": res}

@app.get("/api/post_reposts")
def get_post_reposts(post_id: int):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT username, captured_at FROM twitter_post_reposts 
        WHERE post_id = %s ORDER BY captured_at DESC
    """, (post_id,))
    res = cur.fetchall()
    db.close()
    return {"reposts": res}
# 强行补充 OpenClaw 需要的接口映射
@app.get("/api/projects")
async def get_projects_compatibility():
    return [{"id": "kol-monitor", "name": "KOL Monitor Product", "status": "running"}]
