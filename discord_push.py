"""
Discord Push Notifications - Sends KOL monitoring updates to Discord via webhooks.
Supports 5 channels: posts, following, followers, heatmap, interactions.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from config import DB_DSN

INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINS", "5"))


def send_discord(webhook_url, embed):
    if not webhook_url:
        return False
    data = {"username": "KOL Monitor", "avatar_url": "https://i.imgur.com/g91gVAM.png", "embeds": [embed]}
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    try:
        req = urllib.request.Request(webhook_url, data=json.dumps(data).encode('utf-8'), headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        return 200 <= resp.status < 300
    except Exception as e:
        print(f"  ❌ Discord send error: {e}")
        return False


def get_db():
    return psycopg2.connect(DB_DSN)


def get_user_webhooks(user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT discord_webhook_posts, discord_webhook_interactions,
               discord_webhook_heatmap, discord_webhook_following, discord_webhook_followers
        FROM users WHERE id = %s
    """, (user_id,))
    row = cur.fetchone()
    db.close()
    if not row:
        return None
    return {
        'posts': row.get('discord_webhook_posts'),
        'interactions': row.get('discord_webhook_interactions'),
        'heatmap': row.get('discord_webhook_heatmap'),
        'following': row.get('discord_webhook_following'),
        'followers': row.get('discord_webhook_followers'),
    }


# ============================================================
# CHANNEL 1: x-kol-posts — New posts from the last X minutes
# ============================================================
def push_new_posts(webhook, user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT p.*, k.name as kol_name, k.category
        FROM twitter_posts p
        JOIN kols k ON k.id = p.kol_id
        WHERE k.user_id = %s AND p.is_notified = FALSE
        ORDER BY p.captured_at ASC
    """, (user_id,))
    posts = cur.fetchall()

    if not posts:
        embed = {
            "title": "📝 X KOL Posts Update",
            "description": f"✅ No new posts detected in the last {INTERVAL_MINUTES} minutes.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
        send_discord(webhook, embed)
        db.close()
        print(f"  [Posts] No new posts for user {user_id}")
        return

    print(f"  [Posts] Found {len(posts)} new posts for user {user_id}")
    for post in posts:
        embed = {
            "title": f"📢 New Tweet from {post['kol_name']}",
            "url": post.get('post_url'),
            "description": (post['content'][:1024] if post['content'] else "No content."),
            "color": 0x1DA1F2,
            "fields": [
                {"name": "👍 Likes", "value": str(post['likes'] or 0), "inline": True},
                {"name": "🔁 Retweets", "value": str(post.get('reposts', 0)), "inline": True},
                {"name": "💬 Replies", "value": str(post.get('comments', 0)), "inline": True},
                {"name": "👁️ Views", "value": str(post.get('views', 0)), "inline": True},
                {"name": "🔖 Bookmarks", "value": str(post.get('bookmarks', 0)), "inline": True},
            ],
            "footer": {"text": f"Category: {post['category'] or 'N/A'}"},
            "timestamp": datetime.utcnow().isoformat()
        }
        if send_discord(webhook, embed):
            cur2 = db.cursor()
            cur2.execute("UPDATE twitter_posts SET is_notified = TRUE WHERE id = %s", (post['id'],))
            db.commit()
            print(f"    ✅ {post['kol_name']}: {(post['content'] or '')[:40]}...")
        time.sleep(1.5)

    db.close()


# ============================================================
# CHANNEL 2: x-kol-following — Following count changes
# ============================================================
def push_following_changes(webhook, user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # For each KOL, get the latest 2 metrics snapshots to compare
    cur.execute("""
        WITH ranked AS (
            SELECT m.*, k.name as kol_name,
                   ROW_NUMBER() OVER (PARTITION BY m.kol_id ORDER BY m.captured_at DESC) as rn
            FROM kol_metrics m
            JOIN kols k ON k.id = m.kol_id
            WHERE k.user_id = %s AND m.platform = 'twitter'
        )
        SELECT * FROM ranked WHERE rn <= 2 ORDER BY kol_name, rn
    """, (user_id,))
    rows = cur.fetchall()
    db.close()

    # Group by KOL
    kol_data = {}
    for r in rows:
        name = r['kol_name']
        if name not in kol_data:
            kol_data[name] = []
        kol_data[name].append(r)

    changes = []
    for name, snapshots in kol_data.items():
        if len(snapshots) < 2:
            continue
        current = snapshots[0]['following_count'] or 0
        previous = snapshots[1]['following_count'] or 0
        delta = current - previous
        if delta != 0:
            direction = "📈" if delta > 0 else "📉"
            changes.append(f"{direction} **{name}**: {previous:,} → {current:,} ({'+' if delta > 0 else ''}{delta:,})")

    if not changes:
        embed = {
            "title": "👥 X KOL Following Update",
            "description": f"✅ No following count changes detected in the last {INTERVAL_MINUTES} minutes.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        embed = {
            "title": f"👥 X KOL Following Changes ({len(changes)} KOLs)",
            "description": "\n".join(changes[:20]),
            "color": 0xF39C12,
            "timestamp": datetime.utcnow().isoformat()
        }

    send_discord(webhook, embed)
    print(f"  [Following] {len(changes)} changes for user {user_id}")


# ============================================================
# CHANNEL 3: x-kol-followers — Follower count changes
# ============================================================
def push_follower_changes(webhook, user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        WITH ranked AS (
            SELECT m.*, k.name as kol_name,
                   ROW_NUMBER() OVER (PARTITION BY m.kol_id ORDER BY m.captured_at DESC) as rn
            FROM kol_metrics m
            JOIN kols k ON k.id = m.kol_id
            WHERE k.user_id = %s AND m.platform = 'twitter'
        )
        SELECT * FROM ranked WHERE rn <= 2 ORDER BY kol_name, rn
    """, (user_id,))
    rows = cur.fetchall()
    db.close()

    kol_data = {}
    for r in rows:
        name = r['kol_name']
        if name not in kol_data:
            kol_data[name] = []
        kol_data[name].append(r)

    changes = []
    for name, snapshots in kol_data.items():
        if len(snapshots) < 2:
            continue
        current = snapshots[0]['followers_count'] or 0
        previous = snapshots[1]['followers_count'] or 0
        delta = current - previous
        if delta != 0:
            direction = "📈" if delta > 0 else "📉"
            changes.append(f"{direction} **{name}**: {previous:,} → {current:,} ({'+' if delta > 0 else ''}{delta:,})")

    if not changes:
        embed = {
            "title": "🔔 X KOL Followers Update",
            "description": f"✅ No follower count changes detected in the last {INTERVAL_MINUTES} minutes.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        embed = {
            "title": f"🔔 X KOL Follower Changes ({len(changes)} KOLs)",
            "description": "\n".join(changes[:20]),
            "color": 0xE74C3C,
            "timestamp": datetime.utcnow().isoformat()
        }

    send_discord(webhook, embed)
    print(f"  [Followers] {len(changes)} changes for user {user_id}")


# ============================================================
# CHANNEL 4: x-kol-posts-history (heatmap) — Engagement metrics
# ============================================================
def push_heatmap_report(webhook, user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check for posts with changes in the last 30 minutes
    cur.execute("""
        SELECT p.*, k.name as kol_name
        FROM twitter_posts p
        JOIN kols k ON k.id = p.kol_id
        WHERE k.user_id = %s AND p.captured_at >= NOW() - INTERVAL '30 minutes'
        ORDER BY p.captured_at DESC
    """, (user_id,))
    posts = cur.fetchall()
    db.close()

    if not posts:
        embed = {
            "title": "🔥 X KOL Posts Heatmap Update",
            "description": f"✅ No posts tracked yet.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
        send_discord(webhook, embed)
        print(f"  [Heatmap] No posts for user {user_id}")
        return

    # Find posts with significant engagement changes
    significant = []
    for p in posts:
        d_views = (p['views'] or 0) - (p['last_views'] or 0)
        d_likes = (p['likes'] or 0) - (p['last_likes'] or 0)
        d_reposts = (p['reposts'] or 0) - (p['last_reposts'] or 0)
        d_comments = (p['comments'] or 0) - (p['last_comments'] or 0)
        d_bookmarks = (p['bookmarks'] or 0) - (p['last_bookmarks'] or 0)

        total_delta = d_likes + d_reposts * 3 + d_comments * 5
        if d_views > 100 or d_likes > 5 or d_reposts >= 1 or d_comments >= 1 or d_bookmarks >= 1:
            significant.append({
                'kol': p['kol_name'],
                'url': p['post_url'],
                'content': (p['content'] or '')[:60],
                'views': p['views'] or 0,
                'd_views': d_views,
                'likes': p['likes'] or 0,
                'd_likes': d_likes,
                'reposts': p['reposts'] or 0,
                'd_reposts': d_reposts,
                'comments': p['comments'] or 0,
                'd_comments': d_comments,
                'bookmarks': p['bookmarks'] or 0,
                'd_bookmarks': d_bookmarks,
                'score': total_delta
            })

    significant.sort(key=lambda x: x['score'], reverse=True)

    if not significant:
        embed = {
            "title": "🔥 X KOL Posts Heatmap Update",
            "description": f"✅ No significant engagement changes detected in the last {INTERVAL_MINUTES} minutes across {len(posts)} tracked posts.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
        send_discord(webhook, embed)
        print(f"  [Heatmap] No significant changes for user {user_id}")
        return

    fields = []
    for s in significant[:10]:
        deltas = []
        if s['d_views'] > 0: deltas.append(f"+{s['d_views']:,} views")
        if s['d_likes'] > 0: deltas.append(f"+{s['d_likes']:,} likes")
        if s['d_reposts'] > 0: deltas.append(f"+{s['d_reposts']:,} reposts")
        if s['d_comments'] > 0: deltas.append(f"+{s['d_comments']:,} replies")
        if s['d_bookmarks'] > 0: deltas.append(f"+{s['d_bookmarks']:,} bookmarks")

        fields.append({
            "name": f"🔥 {s['kol']} ({', '.join(deltas)})",
            "value": f"[{s['content']}...]({s['url']})\n"
                     f"📊 Views: {s['views']:,} | 👍 {s['likes']:,} | 🔁 {s['reposts']:,} | 💬 {s['comments']:,} | 🔖 {s['bookmarks']:,}",
            "inline": False
        })

    embed = {
        "title": f"🔥 X KOL Heatmap — {len(significant)} Posts with Engagement Changes",
        "description": f"Tracking {len(posts)} total posts across your KOLs.",
        "color": 0xFF4500,
        "fields": fields,
        "timestamp": datetime.utcnow().isoformat()
    }
    send_discord(webhook, embed)
    print(f"  [Heatmap] {len(significant)} significant changes for user {user_id}")


# ============================================================
# CHANNEL 5: x-kol-posts-interactions — Engagement delta + WHO
# ============================================================
def push_interaction_changes(webhook, user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get posts with ANY engagement delta in the last 30 minutes
    cur.execute("""
        SELECT p.*, k.name as kol_name
        FROM twitter_posts p
        JOIN kols k ON k.id = p.kol_id
        WHERE k.user_id = %s AND p.captured_at >= NOW() - INTERVAL '30 minutes'
        ORDER BY p.captured_at DESC
    """, (user_id,))
    posts = cur.fetchall()

    if not posts:
        embed = {
            "title": "⚡ X KOL Interactions Update",
            "description": f"✅ No posts tracked yet.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
        send_discord(webhook, embed)
        db.close()
        print(f"  [Interactions] No posts for user {user_id}")
        return

    changed_posts = []
    for p in posts:
        d_likes = (p['likes'] or 0) - (p['last_likes'] or 0)
        d_reposts = (p['reposts'] or 0) - (p['last_reposts'] or 0)
        d_comments = (p['comments'] or 0) - (p['last_comments'] or 0)

        if d_likes > 0 or d_reposts > 0 or d_comments > 0:
            # Get recent repliers
            cur.execute("""
                SELECT username FROM twitter_post_replies
                WHERE post_id = %s
                ORDER BY captured_at DESC LIMIT 10
            """, (p['id'],))
            repliers = [r['username'] for r in cur.fetchall()]

            # Get recent reposters
            cur.execute("""
                SELECT username FROM twitter_post_reposts
                WHERE post_id = %s
                ORDER BY captured_at DESC LIMIT 10
            """, (p['id'],))
            reposters = [r['username'] for r in cur.fetchall()]

            changed_posts.append({
                'kol': p['kol_name'],
                'url': p['post_url'],
                'content': (p['content'] or '')[:60],
                'd_likes': d_likes,
                'd_reposts': d_reposts,
                'd_comments': d_comments,
                'likes': p['likes'] or 0,
                'reposts': p['reposts'] or 0,
                'comments': p['comments'] or 0,
                'repliers': repliers,
                'reposters': reposters,
                'score': d_likes + d_reposts * 3 + d_comments * 5
            })

    db.close()

    if not changed_posts:
        embed = {
            "title": "⚡ X KOL Interactions Update",
            "description": f"✅ No interaction changes detected in the last {INTERVAL_MINUTES} minutes across {len(posts)} tracked posts.",
            "color": 0x2ECC71,
            "timestamp": datetime.utcnow().isoformat()
        }
        send_discord(webhook, embed)
        print(f"  [Interactions] No changes for user {user_id}")
        return

    changed_posts.sort(key=lambda x: x['score'], reverse=True)

    fields = []
    for cp in changed_posts[:10]:
        changes = []
        if cp['d_likes'] > 0: changes.append(f"+{cp['d_likes']} likes")
        if cp['d_reposts'] > 0: changes.append(f"+{cp['d_reposts']} reposts")
        if cp['d_comments'] > 0: changes.append(f"+{cp['d_comments']} replies")

        detail_lines = [f"[{cp['content']}...]({cp['url']})"]
        detail_lines.append(f"Current: 👍 {cp['likes']:,} | 🔁 {cp['reposts']:,} | 💬 {cp['comments']:,}")

        if cp['reposters']:
            detail_lines.append(f"↳ Reposted by: {', '.join(['@' + u for u in cp['reposters'][:5]])}")
        if cp['repliers']:
            detail_lines.append(f"↳ Replied by: {', '.join(['@' + u for u in cp['repliers'][:5]])}")

        fields.append({
            "name": f"⚡ {cp['kol']} ({', '.join(changes)})",
            "value": "\n".join(detail_lines),
            "inline": False
        })

    embed = {
        "title": f"⚡ X KOL Interactions — {len(changed_posts)} Posts with Changes",
        "description": f"Tracking {len(posts)} total posts. Showing top {min(len(changed_posts), 10)} by significance.",
        "color": 0x9B59B6,
        "fields": fields,
        "timestamp": datetime.utcnow().isoformat()
    }
    send_discord(webhook, embed)
    print(f"  [Interactions] {len(changed_posts)} changed posts for user {user_id}")


# ============================================================
# MAIN — Run all push jobs for all users
# ============================================================
if __name__ == "__main__":
    import sys
    job_type = sys.argv[1] if len(sys.argv) > 1 else "all"

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users")
    user_ids = [r[0] for r in cur.fetchall()]
    db.close()

    for uid in user_ids:
        print(f"\n📡 Processing Discord push for User {uid}...")
        webhooks = get_user_webhooks(uid)
        if not webhooks:
            print(f"  ⚠️ No webhooks found for user {uid}, skipping.")
            continue

        if job_type in ["posts", "all"]:
            if webhooks.get('posts'):
                push_new_posts(webhooks['posts'], uid)
            else:
                print(f"  ⚠️ No posts webhook for user {uid}")

        if job_type in ["following", "all"]:
            if webhooks.get('following'):
                push_following_changes(webhooks['following'], uid)
            else:
                print(f"  ⚠️ No following webhook for user {uid}")

        if job_type in ["followers", "all"]:
            if webhooks.get('followers'):
                push_follower_changes(webhooks['followers'], uid)
            else:
                print(f"  ⚠️ No followers webhook for user {uid}")

        if job_type in ["heatmap", "all"]:
            if webhooks.get('heatmap'):
                push_heatmap_report(webhooks['heatmap'], uid)
            else:
                print(f"  ⚠️ No heatmap webhook for user {uid}")

        if job_type in ["interactions", "all"]:
            if webhooks.get('interactions'):
                push_interaction_changes(webhooks['interactions'], uid)
            else:
                print(f"  ⚠️ No interactions webhook for user {uid}")

    print("\n✅ All push jobs complete!")
