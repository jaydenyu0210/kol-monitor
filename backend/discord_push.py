"""
Async Discord Push Notifications (Cloud Edition)
Fetches per-user webhook URLs from Supabase user_configs table,
then sends formatted embeds concurrently using httpx.
"""
import asyncio
from datetime import datetime, timedelta

import httpx
import psycopg2
import psycopg2.extras

from db import get_db, release_db
from config import SCRAPE_INTERVAL


def get_all_user_webhooks():
    """Fetch all active webhook configurations from user_configs."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT user_id,
                   discord_webhook_posts, discord_webhook_interactions,
                   discord_webhook_heatmap, discord_webhook_following,
                   discord_webhook_followers
            FROM user_configs
            WHERE discord_webhook_posts IS NOT NULL
               OR discord_webhook_interactions IS NOT NULL
               OR discord_webhook_heatmap IS NOT NULL
               OR discord_webhook_following IS NOT NULL
               OR discord_webhook_followers IS NOT NULL
        """)
        return cur.fetchall()
    finally:
        release_db(db)


async def send_discord_async(webhook_url: str, payload: dict):
    """Send a payload to a single Discord webhook."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(webhook_url, json=payload)
    except Exception as e:
        print(f"⚠️ Discord webhook error: {e}")


async def send_embeds(webhook_url: str, embeds: list):
    """Send a list of embeds to a webhook (Discord allows max 10 per message)."""
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        await send_discord_async(webhook_url, {"embeds": batch})


# ============================================================
# CHANNEL 1: New Posts
# ============================================================

def build_post_embeds(user_id: str, interval_mins: int = SCRAPE_INTERVAL):
    """Build embeds for new posts from the last N minutes."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Only push posts that were BOTH captured recently AND posted recently
        # This prevents old posts from a first-time scrape being pushed.
        since = datetime.utcnow() - timedelta(minutes=interval_mins)
        # We give a small buffer for posted_at (2x interval) to account for scraper delay
        posted_since = datetime.utcnow() - timedelta(minutes=interval_mins * 2)
        
        cur.execute("""
            SELECT tp.*, k.name as kol_name FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s 
              AND tp.captured_at > %s
              AND tp.posted_at > %s
            ORDER BY tp.captured_at DESC
        """, (user_id, since, posted_since))
        posts = cur.fetchall()

        embeds = []
        for p in posts:
            content_preview = (p["content"] or "")[:300]
            embeds.append({
                "title": f"📝 {p['kol_name']} posted",
                "description": content_preview,
                "color": 0x1DA1F2,
                "fields": [
                    {"name": "👍 Likes", "value": str(p.get("likes", 0)), "inline": True},
                    {"name": "💬 Comments", "value": str(p.get("comments", 0)), "inline": True},
                    {"name": "🔄 Reposts", "value": str(p.get("reposts", 0)), "inline": True},
                ],
                "url": p.get("post_url", ""),
                "timestamp": (p.get("posted_at") or datetime.utcnow()).isoformat(),
            })
        return embeds
    finally:
        release_db(db)


# ============================================================
# CHANNEL 2: Following Changes
# ============================================================

def build_following_embeds(user_id: str, interval_mins: int = SCRAPE_INTERVAL):
    """Build embeds for following count changes."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        since = datetime.utcnow() - timedelta(minutes=interval_mins * 2)
        cur.execute("""
            SELECT k.name, m.following_count, m.captured_at
            FROM kol_metrics m JOIN kols k ON m.kol_id = k.id
            WHERE k.user_id = %s AND m.captured_at > %s
            ORDER BY k.name, m.captured_at DESC
        """, (user_id, since))
        rows = cur.fetchall()

        # Group by KOL and detect changes
        by_kol = {}
        for r in rows:
            by_kol.setdefault(r["name"], []).append(r)

        embeds = []
        for name, snapshots in by_kol.items():
            if len(snapshots) >= 2:
                delta = (snapshots[0]["following_count"] or 0) - (snapshots[1]["following_count"] or 0)
                if delta != 0:
                    arrow = "📈" if delta > 0 else "📉"
                    embeds.append({
                        "title": f"{arrow} {name}: Following {'+' if delta > 0 else ''}{delta}",
                        "description": f"Now following **{snapshots[0]['following_count']}** accounts",
                        "color": 0x00C853 if delta > 0 else 0xFF5252,
                    })
        return embeds
    finally:
        release_db(db)


# ============================================================
# CHANNEL 3: Follower Changes
# ============================================================

def build_follower_embeds(user_id: str, interval_mins: int = SCRAPE_INTERVAL):
    """Build embeds for follower count changes."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        since = datetime.utcnow() - timedelta(minutes=interval_mins * 2)
        cur.execute("""
            SELECT k.name, m.followers_count, m.captured_at
            FROM kol_metrics m JOIN kols k ON m.kol_id = k.id
            WHERE k.user_id = %s AND m.captured_at > %s
            ORDER BY k.name, m.captured_at DESC
        """, (user_id, since))
        rows = cur.fetchall()

        by_kol = {}
        for r in rows:
            by_kol.setdefault(r["name"], []).append(r)

        embeds = []
        for name, snapshots in by_kol.items():
            if len(snapshots) >= 2:
                delta = (snapshots[0]["followers_count"] or 0) - (snapshots[1]["followers_count"] or 0)
                if delta != 0:
                    arrow = "📈" if delta > 0 else "📉"
                    embeds.append({
                        "title": f"{arrow} {name}: Followers {'+' if delta > 0 else ''}{delta}",
                        "description": f"Now at **{snapshots[0]['followers_count']}** followers",
                        "color": 0x00C853 if delta > 0 else 0xFF5252,
                    })
        return embeds
    finally:
        release_db(db)


# ============================================================
# CHANNEL 4: Heatmap Report
# ============================================================

def build_heatmap_embeds(user_id: str):
    """Build a summary engagement report."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        since = datetime.utcnow() - timedelta(hours=24)
        cur.execute("""
            SELECT k.name,
                   COUNT(tp.id) as post_count,
                   SUM(tp.likes) as total_likes,
                   SUM(tp.reposts) as total_reposts,
                   SUM(tp.views) as total_views
            FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s AND tp.captured_at > %s
            GROUP BY k.name
            ORDER BY total_likes DESC
        """, (user_id, since))
        rows = cur.fetchall()
        if not rows:
            return []

        lines = []
        for r in rows:
            lines.append(
                f"**{r['name']}**: {r['post_count']} posts | "
                f"❤️ {r['total_likes'] or 0} | 🔄 {r['total_reposts'] or 0} | "
                f"👁️ {r['total_views'] or 0}"
            )

        return [{
            "title": "🔥 24h KOL Engagement Heatmap",
            "description": "\n".join(lines),
            "color": 0xFF6D00,
            "timestamp": datetime.utcnow().isoformat(),
        }]
    finally:
        release_db(db)


# ============================================================
# CHANNEL 5: Interaction Changes (engagement delta)
# ============================================================

def build_interaction_embeds(user_id: str, interval_mins: int = SCRAPE_INTERVAL):
    """Build embeds for engagement changes on existing posts."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT tp.id, k.name as kol_name, tp.content,
                   tp.likes - tp.last_likes as like_delta,
                   tp.reposts - tp.last_reposts as repost_delta,
                   tp.views - tp.last_views as view_delta,
                   tp.comments - tp.last_comments as comment_delta
            FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s
              AND (tp.likes != tp.last_likes OR tp.reposts != tp.last_reposts
                   OR tp.views != tp.last_views OR tp.comments != tp.last_comments)
        """, (user_id,))
        rows = cur.fetchall()

        embeds = []
        for r in rows:
            total_delta = (r["like_delta"] or 0) + (r["repost_delta"] or 0) + (r["comment_delta"] or 0)
            if total_delta > 0:
                embeds.append({
                    "title": f"⚡ {r['kol_name']}: +{total_delta} engagements",
                    "description": (r["content"] or "")[:200],
                    "color": 0x7C4DFF,
                    "fields": [
                        {"name": "❤️ Likes", "value": f"+{r['like_delta'] or 0}", "inline": True},
                        {"name": "🔄 Reposts", "value": f"+{r['repost_delta'] or 0}", "inline": True},
                        {"name": "💬 Comments", "value": f"+{r['comment_delta'] or 0}", "inline": True},
                    ],
                })
        return embeds
    finally:
        release_db(db)


# ============================================================
# MAIN PUSH ORCHESTRATOR
# ============================================================

CHANNEL_MAP = {
    "discord_webhook_posts": build_post_embeds,
    "discord_webhook_following": build_following_embeds,
    "discord_webhook_followers": build_follower_embeds,
    "discord_webhook_heatmap": build_heatmap_embeds,
    "discord_webhook_interactions": build_interaction_embeds,
}


async def push_all_channels(job_filter: str = None):
    """
    Main entry point: for each user with webhooks configured,
    build and send embeds to their active channels concurrently.
    """
    configs = get_all_user_webhooks()
    print(f"📡 Processing Discord push (Filter: {job_filter or 'All'}) for {len(configs)} user(s)...")

    tasks = []
    for config in configs:
        user_id = str(config["user_id"])
        for webhook_key, build_fn in CHANNEL_MAP.items():
            # If a filter is provided (e.g., 'posts'), only process that channel
            if job_filter and job_filter not in webhook_key:
                continue

            webhook_url = config.get(webhook_key)
            if not webhook_url:
                continue

            try:
                if webhook_key == "discord_webhook_heatmap":
                    embeds = build_fn(user_id)
                else:
                    embeds = build_fn(user_id, interval_mins=SCRAPE_INTERVAL)

                if embeds:
                    tasks.append(send_embeds(webhook_url, embeds))
                else:
                    # Provide feedback when there's no new data as requested by user
                    channel_name = webhook_key.replace("discord_webhook_", "").replace("_", " ").capitalize()
                    no_data_msg = {
                        "content": f"ℹ️ **KOL Monitor**: No new updates for **{channel_name}** in the last {SCRAPE_INTERVAL} minutes."
                    }
                    tasks.append(send_discord_async(webhook_url, no_data_msg))
            except Exception as e:
                print(f"⚠️ Error building {webhook_key} for {user_id}: {e}")

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"✅ Sent {len(tasks)} Discord webhook batch(es)")
    else:
        print("ℹ️ No data to push to Discord for this filter")


if __name__ == "__main__":
    import sys
    job_type = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Running Discord Push...")
    asyncio.run(push_all_channels(job_type))
