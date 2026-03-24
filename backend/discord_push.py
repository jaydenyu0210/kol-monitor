"""
Async Discord Push Notifications (Cloud Edition)
Fetches per-user webhook URLs from Supabase user_configs table,
then sends formatted embeds concurrently using httpx.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2
import psycopg2.extras
import json
import os

from db import get_db, release_db
from config import SCRAPE_INTERVAL


def update_feed_cache(user_id, feed_type, items, max_items=50, overwrite=False, metadata=None):
    """Write recent items to a JSON file, mirroring the Discord history."""
    # Ensure items is at least an empty list if we have metadata to write
    if not items and not metadata: return
    
    def default_serializer(obj):
        if isinstance(obj, datetime): return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    clean_items = [dict(item) for item in items] if items else []
    path = f"/app/feed_{feed_type}_{user_id}.json"
    
    existing_items = []
    existing_metadata = None
    
    if not overwrite and os.path.exists(path):
        try:
            with open(path, "r") as f: 
                data = json.load(f)
                if isinstance(data, dict) and "items" in data:
                    existing_items = data["items"]
                    existing_metadata = data.get("metadata")
                else:
                    existing_items = data # Backward compatibility
        except Exception: pass
    
    # Deduplication and history merging
    unified = []
    seen = set()
    for item in clean_items + existing_items:
        key = item.get('post_id') or item.get('id') or item.get('url') or str(item.get('captured_at'))
        if not key: key = json.dumps(item, sort_keys=True)
        if key not in seen:
            unified.append(item)
            seen.add(key)
            
    combined_items = unified[:max_items]
    
    # Final data structure
    final_data = {
        "items": combined_items,
        "metadata": metadata or existing_metadata
    }
    
    try:
        with open(path, "w") as f:
            json.dump(final_data, f, default=default_serializer)
    except Exception as e:
        print(f"  ❌ Cache write error: {e} | Path: {path}")


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
    """Build embeds for new posts that haven't been notified yet, but cache ALL recent posts."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Fetch the actual scrape start time from the DB (the anchor for the window)
        cur.execute("SELECT value FROM system_status WHERE key = %s", (f'twitter_scraper_status_{user_id}',))
        status_row = cur.fetchone()
        status_val = status_row['value'] if status_row and status_row['value'] else {}
        
        last_start_str = status_val.get('last_start_at')
        if last_start_str:
            window_end = datetime.fromisoformat(last_start_str)
        else:
            window_end = datetime.now(timezone.utc)
            
        window_start = window_end - timedelta(minutes=interval_mins)
        
        cur.execute("""
            SELECT tp.*, k.name as kol 
            FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s 
              AND tp.posted_at >= %s
              AND tp.posted_at <= %s
            ORDER BY tp.posted_at DESC
        """, (user_id, window_start.isoformat(), window_end.isoformat()))
        all_recent_posts = cur.fetchall()

        # Update cache with metadata for the Frontend "No results" message
        metadata = {
            "start_time": window_start.isoformat(),
            "end_time": window_end.isoformat(),
            "interval_mins": interval_mins
        }
        update_feed_cache(user_id, 'posts', all_recent_posts, overwrite=True, metadata=metadata)

        # 2. Filter for UNNOTIFIED posts for the actual Discord Push
        unnotified_posts = [p for p in all_recent_posts if not p.get('is_notified')]

        if unnotified_posts:
            # Mark as notified immediately
            post_ids = [p['id'] for p in unnotified_posts]
            if len(post_ids) == 1:
                cur.execute("UPDATE twitter_posts SET is_notified = true WHERE id = %s", (post_ids[0],))
            else:
                cur.execute("UPDATE twitter_posts SET is_notified = true WHERE id IN %s", (tuple(post_ids),))
            db.commit()

        embeds = []
        for p in unnotified_posts:
            content_preview = (p["content"] or "")[:300]
            embeds.append({
                "title": f"📝 {p['kol']} posted",
                "description": content_preview,
                "color": 0x1DA1F2,
                "fields": [
                    {"name": "👍 Likes", "value": str(p.get("likes", 0)), "inline": True},
                    {"name": "💬 Comments", "value": str(p.get("comments", 0)), "inline": True},
                    {"name": "🔄 Reposts", "value": str(p.get("reposts", 0)), "inline": True},
                ],
                "url": p.get("post_url", ""),
                "timestamp": (p.get("posted_at") or datetime.now(timezone.utc)).isoformat(),
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
        # 1. Find the latest changes (delta != 0)
        # Buffer the window to 3x interval to avoid missing data if a scrape cycle lags
        since = datetime.now(timezone.utc) - timedelta(minutes=interval_mins * 3)
        cur.execute("""
            SELECT m1.captured_at, m1.following_count as current, m2.following_count as previous, k.name as kol
            FROM kol_metrics m1
            JOIN kols k ON k.id = m1.kol_id
            LEFT JOIN LATERAL (
                SELECT following_count FROM kol_metrics 
                WHERE kol_id = m1.kol_id AND captured_at < m1.captured_at 
                ORDER BY captured_at DESC LIMIT 1
            ) m2 ON TRUE
            WHERE k.user_id = %s 
              AND m1.captured_at > %s 
              AND m1.following_count != m2.following_count
            ORDER BY k.name, m1.captured_at DESC
        """, (user_id, since))
        rows = cur.fetchall()

        if rows:
            # Add delta for cache/frontend
            for r in rows:
                r['delta'] = (r["current"] or 0) - (r["previous"] or 0)
            update_feed_cache(user_id, 'following', rows, overwrite=False)

        embeds = []
        for r in rows:
            delta = (r["current"] or 0) - (r["previous"] or 0)
            arrow = "📈" if delta > 0 else "📉"
            embeds.append({
                "title": f"{arrow} {r['kol']}: Following {'+' if delta > 0 else ''}{delta}",
                "description": f"Now following **{r['current']}** accounts",
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

        # 1. Find the latest changes (delta != 0) since interval
        # Buffer the window to 3x interval to avoid missing data if a scrape cycle lags
        since = datetime.now(timezone.utc) - timedelta(minutes=interval_mins * 3)
        cur.execute("""
            SELECT m1.captured_at, m1.followers_count as current, m2.followers_count as previous, k.name as kol
            FROM kol_metrics m1
            JOIN kols k ON k.id = m1.kol_id
            LEFT JOIN LATERAL (
                SELECT followers_count FROM kol_metrics 
                WHERE kol_id = m1.kol_id AND captured_at < m1.captured_at 
                ORDER BY captured_at DESC LIMIT 1
            ) m2 ON TRUE
            WHERE k.user_id = %s 
              AND m1.captured_at > %s
              AND m1.followers_count != m2.followers_count
            ORDER BY k.name, m1.captured_at DESC
        """, (user_id, since))
        rows = cur.fetchall()

        if rows:
            # Add delta for cache/frontend
            for r in rows:
                r['delta'] = (r["current"] or 0) - (r["previous"] or 0)
            update_feed_cache(user_id, 'followers', rows, overwrite=False)

        embeds = []
        for r in rows:
            delta = (r["current"] or 0) - (r["previous"] or 0)
            arrow = "📈" if delta > 0 else "📉"
            embeds.append({
                "title": f"{arrow} {r['kol']}: Followers {'+' if delta > 0 else ''}{delta}",
                "description": f"Now at **{r['current']}** followers",
                "color": 0x00C853 if delta > 0 else 0xFF5252,
            })
        return embeds
    finally:
        release_db(db)


def build_heatmap_embeds(user_id: str, interval_mins: int = SCRAPE_INTERVAL):
    """Build a report of individual 'Trending Posts' with significant engagement surges from the latest scrape."""
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get the latest scrape start time to anchor deltas
        # Use user-specific status key
        cur.execute("SELECT value FROM system_status WHERE key = %s", (f'twitter_scraper_status_{user_id}',))
        status_row = cur.fetchone()
        last_start_at = (status_row['value'] if status_row else {}).get('last_start_at')
        
        # 1. Fetch posts with ANY engagement changes in the CURRENT scrape round
        # We look back 2x interval just in case, but anchor to last_start_at for precision
        # Buffer the window to 3x interval to avoid missing data if a scrape cycle lags
        since = datetime.now(timezone.utc) - timedelta(minutes=interval_mins * 3)
        if last_start_at:
            since = last_start_at

        cur.execute("""
            SELECT p.*, k.name as kol_name
            FROM twitter_posts p JOIN kols k ON p.kol_id = k.id
            WHERE k.user_id = %s 
              AND p.captured_at >= %s
              AND (p.likes > p.last_likes OR p.reposts > p.last_reposts OR p.comments > p.last_comments OR p.views > p.last_views)
            ORDER BY p.captured_at DESC
        """, (user_id, since))
        all_changes = cur.fetchall()

        trending_posts = []
        for p in all_changes:
            d_views = (p['views'] or 0) - (p['last_views'] or 0)
            d_likes = (p['likes'] or 0) - (p['last_likes'] or 0)
            d_reposts = (p['reposts'] or 0) - (p['last_reposts'] or 0)
            d_comments = (p['comments'] or 0) - (p['last_comments'] or 0)
            d_bookmarks = (p['bookmarks'] or 0) - (p['last_bookmarks'] or 0)
            
            # Significant Engagement Score: Likes (1), Reposts (3), Comments/Replies (5), Bookmarks (2)
            # We also consider views (1 pt per 1000 views)
            score = d_likes + (d_reposts * 3) + (d_comments * 5) + (d_bookmarks * 2) + (d_views // 1000)
            
            # Threshold: Support "Significant changes in views, likes, reposts, replies, bookmarks, comments"
            # Flag if Score >= 10 OR any field had a manual significant bump
            if score >= 10 or d_views >= 1000 or d_bookmarks >= 5 or d_comments >= 3:
                trending_posts.append({
                    'kol': p['kol_name'], 'url': p['post_url'], 'content': (p['content'] or '')[:300],
                    'views': p['views'] or 0, 'd_views': d_views,
                    'likes': p['likes'] or 0, 'd_likes': d_likes,
                    'reposts': p['reposts'] or 0, 'd_reposts': d_reposts,
                    'comments': p['comments'] or 0, 'd_comments': d_comments,
                    'bookmarks': p['bookmarks'] or 0, 'd_bookmarks': d_bookmarks,
                    'score': score,
                    'captured_at': p['captured_at']
                })

        # 2. Update Cache (Sort by recent first, then by score)
        # Identical matching: webpage and Discord now both show the FULL list of significant posts.
        trending_posts.sort(key=lambda x: (x['captured_at'], x['score']), reverse=True)
        update_feed_cache(user_id, 'heatmap', trending_posts, overwrite=True)

        if not trending_posts:
            return []

        # 3. Build Embeds for ALL Trending Posts for Discord
        embeds = []
        for p in trending_posts:
            embeds.append({
                "title": f"🔥 Trending: {p['kol']}",
                "description": p['content'],
                "color": 0xFF6D00,
                "url": p['url'],
                "fields": [
                    {"name": "📈 Score", "value": f"**+{p['score']}**", "inline": True},
                    {"name": "❤️ Likes", "value": f"+{p['d_likes']}", "inline": True},
                    {"name": "🔄 Reposts", "value": f"+{p['d_reposts']}", "inline": True},
                    {"name": "👁️ Views", "value": f"+{p['d_views']}", "inline": True},
                    {"name": "🔖 Bookmarks", "value": f"+{p['d_bookmarks']}", "inline": True},
                ],
                "footer": {"text": "Detected in last scrap round"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        return embeds
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
        
        # Get the latest scrape start time to anchor deltas
        # Use user-specific status key
        cur.execute("SELECT value FROM system_status WHERE key = %s", (f'twitter_scraper_status_{user_id}',))
        status_row = cur.fetchone()
        last_start_at = (status_row['value'] if status_row else {}).get('last_start_at')

        # 1. Fetch interaction changes since interval
        # Buffer the window to 3x interval to avoid missing data if a scrape cycle lags
        since = datetime.now(timezone.utc) - timedelta(minutes=interval_mins * 3)
        if last_start_at:
            since = last_start_at

        cur.execute("""
            SELECT tp.id, k.name as kol, tp.content, tp.post_url,
                   tp.likes, tp.reposts, tp.views, tp.comments,
                   tp.likes - tp.last_likes as like_delta,
                   tp.reposts - tp.last_reposts as repost_delta,
                   tp.views - tp.last_views as view_delta,
                   tp.comments - tp.last_comments as comment_delta,
                   tp.captured_at
            FROM twitter_posts tp
            JOIN kols k ON tp.kol_id = k.id
            WHERE k.user_id = %s
              AND (tp.captured_at >= %s OR tp.first_captured_at >= %s)
              AND (tp.likes != tp.last_likes OR tp.reposts != tp.last_reposts
                   OR tp.views != tp.last_views OR tp.comments != tp.last_comments)
            ORDER BY tp.captured_at DESC
        """, (user_id, since, since))
        rows = cur.fetchall()

        if rows:
            cache_items = []
            significant_rows = []
            for r in rows:
                # Significant Interaction Threshold: >= 5 total changes
                total_delta = (r["like_delta"] or 0) + (r["repost_delta"] or 0) + (r["comment_delta"] or 0)
                if total_delta < 5:
                    continue
                
                significant_rows.append(r)

                # Get recent repliers/reposters
                cur.execute("SELECT username FROM twitter_post_replies WHERE post_id = %s ORDER BY captured_at DESC LIMIT 5", (r['id'],))
                repliers = [res['username'] for res in cur.fetchall()]
                cur.execute("SELECT username FROM twitter_post_reposts WHERE post_id = %s ORDER BY captured_at DESC LIMIT 5", (r['id'],))
                reposters = [res['username'] for res in cur.fetchall()]
                
                cache_items.append({
                    'kol': r['kol'], 'url': r['post_url'], 'content': (r['content'] or '')[:120],
                    'd_likes': r['like_delta'] or 0, 'd_reposts': r['repost_delta'] or 0, 'd_comments': r['comment_delta'] or 0,
                    'likes': r['likes'] or 0, 'reposts': r['reposts'] or 0, 'comments': r['comments'] or 0,
                    'repliers': repliers, 'reposters': reposters
                })
            update_feed_cache(user_id, 'interactions', cache_items, overwrite=True)
            rows = significant_rows

        embeds = []
        for r in rows:
            total_delta = (r["like_delta"] or 0) + (r["repost_delta"] or 0) + (r["comment_delta"] or 0)
            embeds.append({
                "title": f"⚡ {r['kol']}: +{total_delta} engagements",
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
        
        # [NEW] Optional filter to only push for a specific user (ideal for local development)
        limit_user = os.getenv("LIMIT_TO_USER_ID")
        if limit_user and user_id != limit_user:
            continue

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
                elif webhook_key == "discord_webhook_posts" and (job_filter is None or job_filter == "posts"):
                    # The user wants an update even if none found: "even if no new posts, say new posts"
                    tasks.append(send_embeds(webhook_url, [{
                        "title": "📝 New X Posts",
                        "description": "No new posts found in this scrape interval.",
                        "color": 0x2C2F33, # Dark grey (Discord background flavor)
                        "footer": {"text": f"Scrape Interval: {SCRAPE_INTERVAL}m | Check Complete"}
                    }]))
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
    print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Running Discord Push...")
    asyncio.run(push_all_channels(job_type))
