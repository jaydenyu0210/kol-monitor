"""
Twitter/X KOL Monitor - Scrapes Twitter profiles using Playwright with cookies.
"""

import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone, timedelta

import psycopg2
import psycopg2.extras
from playwright.async_api import async_playwright
from db import get_db, release_db
from config import HEADLESS, SLOW_MO

# Logging filter: only print logs for specific user if LOG_USER_ID is set
_LOG_USER_ID = os.getenv("LOG_USER_ID")

def should_log(user_id=None):
    """Returns True if we should log this message (based on LOG_USER_ID env var)."""
    if not _LOG_USER_ID:
        return True  # Log all by default
    return user_id == _LOG_USER_ID

def log_print(*args, **kwargs):
    """Print wrapper that respects LOG_USER_ID filter."""
    user_id = kwargs.pop('user_id', None)
    if should_log(user_id):
        print(*args, **kwargs)

def make_status_key(user_id=None):
    env_suffix = os.getenv("ENVIRONMENT_NAME", "Local").replace(" ", "_").lower()
    base = "twitter_scraper_status"
    if env_suffix:
        base = f"{base}_{env_suffix}"
    if user_id:
        base = f"{base}_{user_id}"
    return base

def get_kols(db):
    cur = db.cursor()
    cur.execute("SELECT id, name, twitter_url FROM kols WHERE status='active' AND twitter_url IS NOT NULL ORDER BY id")
    return cur.fetchall()

def update_scrape_status(db, message, user_id=None, extra=None):
    """Update the current activity in the system_status table, partitioned by user if provided."""
    try:
        cur = db.cursor()
        key = make_status_key(user_id)
            
        cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
        row = cur.fetchone()
        status = row[0] if row else {}
        
        status['current_activity'] = message
        if extra:
            status.update(extra)
        
        # Maintain a log history (last 50 lines) to help isolated user debugging
        logs = status.get('logs', [])
        # Only add if the message is new or significant (avoid duplicates of 'Idle')
        if not logs or logs[-1] != f"[{datetime.now().strftime('%H:%M:%S')}] {message}":
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            status['logs'] = logs[-50:] # Keep last 50 entries
        
        cur.execute("""
            INSERT INTO system_status (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(status)))
        db.commit()
    except Exception as e:
        print(f"⚠️ Failed to update activity status: {e}")

def get_twitter_username(url):
    match = re.search(r'x\.com/(\w+)', url)
    return match.group(1) if match else None

def parse_count(text):
    if not text: return 0
    text = text.replace(',', '').strip().lower()
    multipliers = {'k': 1000, 'm': 1000000}
    matches = re.findall(r'(\d+(?:\.\d+)?)([km]?)', text)
    if not matches: return 0
    val_str, suffix = matches[0]
    val = float(val_str)
    if suffix in multipliers:
        val *= multipliers[suffix]
    return int(val)

async def scrape_post_interactions(page, db, twitter_post_id, tweet_url, interaction_type="replies"):
    import random
    print(f"  🔥 Scraping {interaction_type} for: {tweet_url}")
    
    try:
        # Navigate to the status page
        await page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        
        # If we want reposters, we need to click the reposts count
        if interaction_type == "reposts":
             try:
                 # Try to find and click the reposts button/link
                 repost_link = await page.query_selector('a[href$="/retweets"]')
                 if repost_link:
                     await repost_link.click()
                     await page.wait_for_timeout(1500)
             except: pass

        usernames = set()
        
        # Human-like scrolling loop
        max_scrolls = 10
        for i in range(max_scrolls):
            # Find all user tags
            cells = await page.query_selector_all('div[data-testid="User-Name"]')
            for cell in cells:
                links = await cell.query_selector_all('a[href^="/"]')
                for link in links:
                    href = await link.get_attribute('href')
                    if href and not any(x in href.lower() for x in ['/status/', '/home', '/explore', '/messages', '/notifications']):
                        username = href.strip('/')
                        if username and username.lower() not in ['settings', 'tos', 'privacy']:
                            usernames.add(username)
            
            if len(usernames) >= 150: break
            
            # Scroll down with jitter
            scroll_amt = random.randint(400, 900)
            await page.evaluate(f"window.scrollBy(0, {scroll_amt})")
            
            # Random wait (human "reading" time)
            await page.wait_for_timeout(random.randint(800, 1500))

        # Save to DB
        cur = db.cursor()
        table = "twitter_post_replies" if interaction_type == "replies" else "twitter_post_reposts"
        saved = 0
        for uname in usernames:
            try:
                cur.execute(f"""
                    INSERT INTO {table} (post_id, username)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (twitter_post_id, uname))
                saved += cur.rowcount
            except: pass
        
        db.commit()
        print(f"    ✅ Saved {saved} unique interactors to {table}")
        
    except Exception as e:
        print(f"  ⚠️ Error scraping {interaction_type}: {e}")
        db.rollback()

async def scrape_profile(page, kol_id, name, url, db, sync_time, user_id=None, search_counter=None):
    start_ts = datetime.now(timezone.utc)
    msg = f"Scraping {name} (@{get_twitter_username(url)})"
    log_print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", user_id=user_id)
    update_scrape_status(db, msg, user_id=user_id)
    
    try:
        # Skip profile page visit — go directly to search to save rate limit budget
        username = get_twitter_username(url)

        # Search each calendar day in the last 7 days (clean date-aligned windows)
        today = sync_time.date()
        cutoff_date = sync_time - timedelta(days=7)
        seen_ids = set()
        collected = []
        per_day_counts = {}

        async def scrape_day(since_date, until_date):
            """Scrape one calendar day: since_date (inclusive) to until_date (exclusive)."""
            nonlocal collected
            day_label = since_date.isoformat()
            search_url = f"https://x.com/search?q=from%3A{username}%20since%3A{since_date.isoformat()}%20until%3A{until_date.isoformat()}&src=typed_query&f=live"
            log_print(f"  🔎 Day {day_label}: {search_url}", user_id=user_id)
            # Brief random pre-navigation pause to mimic human browsing
            await page.wait_for_timeout(random.randint(1000, 2500))
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for actual search results or empty state instead of fixed delay
            try:
                await page.wait_for_selector(
                    'article[data-testid="tweet"], [data-testid="emptyState"]',
                    timeout=10000
                )
            except:
                # Timeout — check if we hit a rate limit or error page
                content = await page.content()
                content_lower = content.lower()
                if "rate limit" in content_lower or "something went wrong" in content_lower:
                    log_print(f"  ⚠️ Rate limited during search for {day_label}, signaling upstream", user_id=user_id)
                    per_day_counts[day_label] = -1  # signal rate limit
                    return
            await page.wait_for_timeout(800)  # brief settle time

            # Check for empty state and skip immediately if no results
            empty = await page.query_selector('[data-testid="emptyState"]')
            if empty:
                per_day_counts[day_label] = 0
                log_print(f"  🧭 Day {day_label}: no results (empty state)", user_id=user_id)
                return

            # Also check for error/rate limit content in the page body
            page_text = await page.inner_text('body') if await page.query_selector('body') else ''
            if 'something went wrong' in page_text.lower() or 'rate limit' in page_text.lower():
                log_print(f"  ⚠️ Error page detected during search for {day_label}", user_id=user_id)
                per_day_counts[day_label] = -1  # signal rate limit
                return

            day_seen = 0
            stale = 0
            last_seen_local = 0
            for _ in range(220):  # deep enough for a single day but faster
                articles = await page.query_selector_all('article[data-testid=\"tweet\"]')
                for tweet in articles:
                    link = await tweet.query_selector('a[href*=\"/status/\"]')
                    if not link:
                        continue
                    href = await link.get_attribute('href')
                    if not href:
                        continue
                    tid = href.split('/')[-1]
                    post_id = f"tw_{tid}"
                    if post_id in seen_ids:
                        continue

                    time_el = await tweet.query_selector('time')
                    posted_at = await time_el.get_attribute('datetime') if time_el else None
                    if not posted_at:
                        continue

                    # Accept all tweets returned by the search (Twitter handles filtering)
                    # No need for strict day_start/day_end filter since search is already 1 day

                    # Debug: log first tweet's engagement DOM for diagnostics
                    if day_seen == 0 and len(seen_ids) == 0:
                        try:
                            _dbg_group = await tweet.query_selector('[role="group"]')
                            if _dbg_group:
                                _dbg_aria = await _dbg_group.get_attribute('aria-label')
                                _dbg_html = await _dbg_group.inner_html()
                                log_print(f"    🔍 DEBUG first tweet group aria-label: {_dbg_aria}", user_id=user_id)
                                log_print(f"    🔍 DEBUG first tweet group HTML (first 500): {_dbg_html[:500]}", user_id=user_id)
                            else:
                                _dbg_html = await tweet.inner_html()
                                log_print(f"    🔍 DEBUG no [role=group] in first tweet, HTML (first 800): {_dbg_html[:800]}", user_id=user_id)
                        except Exception as _dbg_e:
                            log_print(f"    🔍 DEBUG error inspecting first tweet: {_dbg_e}", user_id=user_id)

                    # Extract counts
                    likes = '0'; reposts = '0'; replies = '0'; bookmarks = '0'; views = '0'
                    group = await tweet.query_selector('[role="group"]')
                    if group:
                        aria = await group.get_attribute('aria-label')
                        if aria:
                            replies_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+repl(?:y|ies)', aria, re.I)
                            reposts_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+repost(?:s)?', aria, re.I)
                            likes_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+like(?:s)?', aria, re.I)
                            bookmarks_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+bookmark(?:s)?', aria, re.I)
                            views_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+view(?:s)?', aria, re.I)
                            if replies_match: replies = replies_match.group(1)
                            if reposts_match: reposts = reposts_match.group(1)
                            if likes_match: likes = likes_match.group(1)
                            if bookmarks_match: bookmarks = bookmarks_match.group(1)
                            if views_match: views = views_match.group(1)
                        else:
                            log_print(f"    ⚠️ [role=group] found but no aria-label for {post_id}", user_id=user_id)

                        # Fallback: extract from individual button aria-labels if group aria-label failed
                        if likes == '0' and reposts == '0' and replies == '0':
                            btn_map = {
                                'reply': ('replies', r'([\d.,]+[KMkm]?)'),
                                'retweet': ('reposts', r'([\d.,]+[KMkm]?)'),
                                'like': ('likes', r'([\d.,]+[KMkm]?)'),
                                'bookmark': ('bookmarks', r'([\d.,]+[KMkm]?)'),
                            }
                            for testid, (metric, pat) in btn_map.items():
                                btn = await group.query_selector(f'button[data-testid="{testid}"]')
                                if btn:
                                    btn_aria = await btn.get_attribute('aria-label') or ''
                                    m = re.search(pat, btn_aria)
                                    if m:
                                        val = m.group(1)
                                        if testid == 'reply': replies = val
                                        elif testid == 'retweet': reposts = val
                                        elif testid == 'like': likes = val
                                        elif testid == 'bookmark': bookmarks = val
                            if likes != '0' or reposts != '0' or replies != '0':
                                log_print(f"    🔄 Used button fallback for {post_id}: L={likes} R={reposts} C={replies} B={bookmarks}", user_id=user_id)
                    else:
                        log_print(f"    ⚠️ No [role=group] found for {post_id}", user_id=user_id)

                    if views == '0':
                        views_el = await tweet.query_selector('a[href*="/analytics"]')
                        if views_el:
                            views_aria = await views_el.get_attribute('aria-label') or ''
                            views_m = re.search(r'([\d.,]+[KMkm]?)', views_aria)
                            if views_m:
                                views = views_m.group(1)
                        # Fallback: try span inside analytics link
                        if views == '0':
                            views_span = await tweet.query_selector('a[href*="/analytics"] span span')
                            if views_span:
                                views_text = (await views_span.inner_text()).strip()
                                if views_text and views_text != '0':
                                    views = views_text

                    tweet_text_el = await tweet.query_selector('div[data-testid=\"tweetText\"]')
                    tweet_text = await tweet_text_el.inner_text() if tweet_text_el else ''
                    tweet_url = "https://x.com" + href

                    collected.append({
                        'post_id': post_id,
                        'url': tweet_url,
                        'content': tweet_text,
                        'posted_at': posted_at,
                        'likes': parse_count(likes),
                        'reposts': parse_count(reposts),
                        'comments': parse_count(replies),
                        'bookmarks': parse_count(bookmarks),
                        'views': parse_count(views)
                    })
                    seen_ids.add(post_id)
                    day_seen += 1

                if day_seen == last_seen_local:
                    stale += 1
                else:
                    stale = 0
                last_seen_local = day_seen

                if stale >= 5:
                    break

                await page.evaluate("window.scrollBy(0, 1500)")
                await page.wait_for_timeout(random.randint(700, 1200))

            per_day_counts[day_label] = day_seen
            log_print(f"  🧭 Day {day_label}: captured {day_seen} posts", user_id=user_id)

        # Tiered day scraping to handle 10+ KOLs within Twitter's rate limits:
        # - Today + yesterday: ALWAYS scraped (fresh content + engagement)
        # - Days 2-7: only scraped if not captured in the last 60 minutes
        # - Retry optimization: skip any day scraped within last 15 minutes
        cur_recent = db.cursor()

        # Get days scraped in last 15 minutes (for retry skip)
        cur_recent.execute("""
            SELECT DATE(posted_at) as post_date
            FROM twitter_posts
            WHERE kol_id = %s AND captured_at >= %s
            GROUP BY DATE(posted_at)
        """, (kol_id, sync_time - timedelta(minutes=15)))
        very_recent = {str(row[0]) for row in cur_recent.fetchall()}

        # Get days scraped in last 60 minutes (older days can be skipped)
        cur_recent.execute("""
            SELECT DATE(posted_at) as post_date
            FROM twitter_posts
            WHERE kol_id = %s AND captured_at >= %s
            GROUP BY DATE(posted_at)
        """, (kol_id, sync_time - timedelta(minutes=60)))
        recent_60m = {str(row[0]) for row in cur_recent.fetchall()}

        # Check if this KOL has ANY posts in DB at all (for empty accounts)
        cur_recent.execute("SELECT COUNT(*) FROM twitter_posts WHERE kol_id = %s", (kol_id,))
        total_historical = cur_recent.fetchone()[0]
        max_days = 2 if total_historical == 0 else 8

        day_windows = []
        skipped_recent = 0
        skipped_stale = 0
        for i in range(max_days):
            d = today - timedelta(days=i)
            day_str = d.isoformat()
            # Always skip days scraped very recently (retry optimization)
            if day_str in very_recent:
                log_print(f"  ⏭️  Day {day_str}: skipping (scraped <15m ago)", user_id=user_id)
                skipped_recent += 1
            # For older days (2+), skip if scraped within last 60 minutes
            elif i >= 2 and day_str in recent_60m:
                log_print(f"  ⏭️  Day {day_str}: skipping (scraped <60m ago)", user_id=user_id)
                skipped_stale += 1
            else:
                day_windows.append((d, d + timedelta(days=1)))

        total_skipped = skipped_recent + skipped_stale + (8 - max_days)
        if total_skipped > 0:
            log_print(f"  📋 Will scrape {len(day_windows)} days (skipped {total_skipped}: {skipped_recent} retry, {skipped_stale} stale, {8 - max_days} empty-KOL)", user_id=user_id)

        def save_partial_results():
            """Save whatever we've collected so far to DB."""
            if not collected:
                return
            partial_cur = db.cursor()
            count = 0
            for item in collected:
                try:
                    partial_cur.execute("""
                        INSERT INTO twitter_posts (
                            kol_id, post_id, content, likes, reposts, comments, bookmarks, views, post_url, posted_at,
                            first_captured_at, captured_at,
                            last_likes, last_reposts, last_comments, last_bookmarks, last_views
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (post_id) DO UPDATE SET
                            last_likes = CASE WHEN GREATEST(EXCLUDED.likes, twitter_posts.likes) != twitter_posts.likes THEN twitter_posts.likes ELSE twitter_posts.last_likes END,
                            last_reposts = CASE WHEN GREATEST(EXCLUDED.reposts, twitter_posts.reposts) != twitter_posts.reposts THEN twitter_posts.reposts ELSE twitter_posts.last_reposts END,
                            last_comments = CASE WHEN GREATEST(EXCLUDED.comments, twitter_posts.comments) != twitter_posts.comments THEN twitter_posts.comments ELSE twitter_posts.last_comments END,
                            last_bookmarks = CASE WHEN GREATEST(EXCLUDED.bookmarks, twitter_posts.bookmarks) != twitter_posts.bookmarks THEN twitter_posts.bookmarks ELSE twitter_posts.last_bookmarks END,
                            last_views = CASE WHEN GREATEST(EXCLUDED.views, twitter_posts.views) != twitter_posts.views THEN twitter_posts.views ELSE twitter_posts.last_views END,
                            likes = GREATEST(EXCLUDED.likes, twitter_posts.likes),
                            reposts = GREATEST(EXCLUDED.reposts, twitter_posts.reposts),
                            comments = GREATEST(EXCLUDED.comments, twitter_posts.comments),
                            bookmarks = GREATEST(EXCLUDED.bookmarks, twitter_posts.bookmarks),
                            views = GREATEST(EXCLUDED.views, twitter_posts.views),
                            captured_at = EXCLUDED.captured_at
                    """, (
                        kol_id, item['post_id'], item['content'], item['likes'], item['reposts'], item['comments'], item['bookmarks'], item['views'],
                        item['url'], item['posted_at'], sync_time, sync_time,
                        item['likes'], item['reposts'], item['comments'], item['bookmarks'], item['views']
                    ))
                    count += 1
                except Exception:
                    pass
            db.commit()
            log_print(f"  💾 Saved {count} partial results before context rotation", user_id=user_id)

        rate_limited_days = 0
        for since_date, until_date in day_windows:
            await scrape_day(since_date, until_date)
            if search_counter is not None:
                search_counter[0] += 1
            # Check if the day was rate-limited (signaled by -1)
            day_label = since_date.isoformat()
            if per_day_counts.get(day_label) == -1:
                rate_limited_days += 1
                if rate_limited_days >= 2:
                    log_print(f"  ⚠️ Session degraded ({rate_limited_days} rate-limited days). Stopping early.", user_id=user_id)
                    save_partial_results()
                    return "session_degraded"
                # First rate limit — cool down before trying next day
                log_print(f"  ⏳ Rate limit cooldown: sleeping 90s...", user_id=user_id)
                await asyncio.sleep(90)
            # Progressive delay between day searches based on cumulative search count
            total_searches = search_counter[0] if search_counter else 0
            if total_searches > 30:
                delay = random.randint(10000, 15000)
            elif total_searches > 20:
                delay = random.randint(8000, 12000)
            elif total_searches > 10:
                delay = random.randint(6000, 9000)
            else:
                delay = random.randint(5000, 8000)
            await page.wait_for_timeout(delay)

        # --- Scrape Profile Metrics (once after search loops) ---
        
        # --- Scrape Profile Metrics ---
        metrics = {}
        try:
            following_el = await page.query_selector(f'a[href="/{get_twitter_username(url)}/following"]')
            if following_el:
                following_text = await following_el.text_content()
                metrics['following'] = parse_count(following_text)
            
            followers_el = await page.query_selector(f'a[href="/{get_twitter_username(url)}/verified_followers"]')
            if not followers_el:
                followers_el = await page.query_selector(f'a[href="/{get_twitter_username(url)}/followers"]')
            if followers_el:
                followers_text = await followers_el.text_content()
                metrics['followers'] = parse_count(followers_text)
        except Exception as e:
            log_print(f"  ⚠️  Could not parse metrics for {name}: {e}", user_id=user_id)

        cur = db.cursor()
        if metrics:
            cur.execute("""
                INSERT INTO kol_metrics (kol_id, platform, followers_count, following_count, captured_at)
                VALUES (%s, 'twitter', %s, %s, %s)
            """, (kol_id, metrics.get('followers'), metrics.get('following'), sync_time))
            log_print(f"  📊 Metrics: Followers: {metrics.get('followers')}, Following: {metrics.get('following')}", user_id=user_id)

        # --- Scrape Recent Tweets (from collected search results) ---
        tweet_count = 0
        skipped_count = 0
        processed_tweets = []
        
        log_print(f"  🔍 Inserting {len(collected)} collected tweets from search windows...", user_id=user_id)

        for item in collected:
            try:
                posted_at = item['posted_at']
                cur.execute("""
                    INSERT INTO twitter_posts (
                        kol_id, post_id, content, likes, reposts, comments, bookmarks, views, post_url, posted_at, 
                        first_captured_at, captured_at, 
                        last_likes, last_reposts, last_comments, last_bookmarks, last_views
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (post_id) DO UPDATE SET
                        last_likes = CASE WHEN GREATEST(EXCLUDED.likes, twitter_posts.likes) != twitter_posts.likes THEN twitter_posts.likes ELSE twitter_posts.last_likes END,
                        last_reposts = CASE WHEN GREATEST(EXCLUDED.reposts, twitter_posts.reposts) != twitter_posts.reposts THEN twitter_posts.reposts ELSE twitter_posts.last_reposts END,
                        last_comments = CASE WHEN GREATEST(EXCLUDED.comments, twitter_posts.comments) != twitter_posts.comments THEN twitter_posts.comments ELSE twitter_posts.last_comments END,
                        last_bookmarks = CASE WHEN GREATEST(EXCLUDED.bookmarks, twitter_posts.bookmarks) != twitter_posts.bookmarks THEN twitter_posts.bookmarks ELSE twitter_posts.last_bookmarks END,
                        last_views = CASE WHEN GREATEST(EXCLUDED.views, twitter_posts.views) != twitter_posts.views THEN twitter_posts.views ELSE twitter_posts.last_views END,
                        likes = GREATEST(EXCLUDED.likes, twitter_posts.likes),
                        reposts = GREATEST(EXCLUDED.reposts, twitter_posts.reposts),
                        comments = GREATEST(EXCLUDED.comments, twitter_posts.comments),
                        bookmarks = GREATEST(EXCLUDED.bookmarks, twitter_posts.bookmarks),
                        views = GREATEST(EXCLUDED.views, twitter_posts.views),
                        captured_at = EXCLUDED.captured_at
                    RETURNING id
                """, (
                    kol_id, item['post_id'], item['content'], item['likes'], item['reposts'], item['comments'], item['bookmarks'], item['views'],
                    item['url'], posted_at, sync_time, sync_time,
                    item['likes'], item['reposts'], item['comments'], item['bookmarks'], item['views']
                ))
                db_post_id = cur.fetchone()[0]
                processed_tweets.append({'db_id': db_post_id, 'url': item['url'], 'replies': item['comments'], 'reposts': item['reposts']})
                tweet_count += 1
            except Exception as e:
                log_print(f"  ⚠️  Error inserting tweet for {name}: {e}", user_id=user_id)
                skipped_count += 1

        # Count total stored for this KOL in the 7-day window for verification
        cur.execute("SELECT COUNT(*) FROM twitter_posts WHERE kol_id = %s AND (posted_at > %s OR (posted_at IS NULL AND captured_at > %s))", (kol_id, cutoff_date, cutoff_date))
        total_stored = cur.fetchone()[0]
        
        db.commit()
        if per_day_counts:
            breakdown = ", ".join([f"{k}: {v}" for k, v in sorted(per_day_counts.items())])
            log_print(f"  📅 Daily counts: {breakdown}", user_id=user_id)
        elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
        unique_posts = len(seen_ids)
        log_print(f"  ✅ Finished @{get_twitter_username(url)} in {elapsed:.1f}s: {tweet_count} inserted/updated, {skipped_count} skipped. [Total 7d History: {total_stored} posts | Unique posts seen: {unique_posts} | Days scraped: {len(per_day_counts)}]", user_id=user_id)
        
        # Interaction scraping disabled for speed — each one adds a full page load
        # Uncomment to re-enable for detailed reply/repost usernames:
        # for pt in processed_tweets:
        #     if pt['replies'] > 15:
        #         await scrape_post_interactions(page, db, pt['db_id'], pt['url'], "replies")
        #     if pt['reposts'] > 15:
        #         await scrape_post_interactions(page, db, pt['db_id'], pt['url'], "reposts")
        
        # Mark KOL as updated today
        cur.execute("UPDATE kols SET updated_at = %s WHERE id = %s", (sync_time, kol_id))
        db.commit()

        return True

    except Exception as e:
        log_print(f"  ❌ Error scraping {name}: {e}", user_id=user_id)
        db.rollback()
        return False

async def main():
    db = get_db()
    sync_time = datetime.now(timezone.utc)
    # Track total search requests across all KOLs to pace ourselves
    global_search_count = 0
    try:
        # Scrape by User isolation
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
        users = [str(r['user_id']) for r in cur.fetchall()]

        # Optional filter to only scrape specific users (comma-separated)
        limit_users_env = os.getenv("LIMIT_TO_USER_IDS")
        limit_user = os.getenv("LIMIT_TO_USER_ID")
        target_users = None
        if limit_users_env:
            target_users = [u.strip() for u in limit_users_env.split(",") if u.strip()]
        elif limit_user:
            target_users = [limit_user]

        if target_users:
            filtered = [u for u in users if u in target_users]
            if not filtered:
                print(f"⚠️ LIMIT_TO_USER_IDS/LIMIT_TO_USER_ID set but no active KOLs found. Skipping scrape.")
                return
            users = filtered

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=HEADLESS, args=['--no-sandbox'])
            
            for user_id in users:
                log_print(f"--- Starting Scrape for User ID: {user_id} ---", user_id=user_id)
                
                # Fetch X cookies from user_configs table
                cur.execute("SELECT twitter_auth_token, twitter_ct0 FROM user_configs WHERE user_id = %s", (user_id,))
                config_row = cur.fetchone()
                
                if not config_row or not config_row.get('twitter_auth_token'):
                    log_print(f"⚠️ User {user_id}: No X cookies configured. Skipping.", user_id=user_id)
                    continue
                
                user_auth = config_row['twitter_auth_token']
                user_ct0 = config_row['twitter_ct0']

                context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
                await context.add_cookies([
                    {'name': 'auth_token', 'value': user_auth, 'domain': '.x.com', 'path': '/'},
                    {'name': 'ct0', 'value': user_ct0, 'domain': '.x.com', 'path': '/'}
                ])
                
                page = await context.new_page()
                try:
                    await page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
                    
                    if "login" in page.url:
                        log_print(f"❌ User {user_id}: Twitter/X login failed with cookies!", user_id=user_id)
                        update_scrape_status(db, f"❌ Login failed", user_id)
                        await context.close()
                        continue
                    log_print(f"✅ User {user_id}: Twitter/X login successful!", user_id=user_id)
                    await page.close()  # Close login-test page; fresh pages created per KOL
                    # Initialize session-level progress state
                    cur2 = db.cursor()
                    # Smart ordering: lightest KOLs first, heaviest last
                    # This ensures lighter KOLs finish before rate limit budget is consumed
                    cur2.execute("""
                        SELECT k.id, k.name, k.twitter_url,
                               COALESCE(pc.cnt, 0) as post_count
                        FROM kols k
                        LEFT JOIN (
                            SELECT kol_id, COUNT(*) as cnt
                            FROM twitter_posts
                            WHERE captured_at >= NOW() - INTERVAL '7 days'
                            GROUP BY kol_id
                        ) pc ON k.id = pc.kol_id
                        WHERE k.status = 'active' AND k.user_id = %s
                        ORDER BY post_count ASC
                    """, (user_id,))
                    kols_raw = cur2.fetchall()
                    kols = [(r[0], r[1], r[2]) for r in kols_raw]
                    kol_order = ", ".join([f"{r[1]}({r[3]})" for r in kols_raw])
                    log_print(f"📋 KOL order (lightest first): {kol_order}", user_id=user_id)
                    total_kols = len(kols)
                    scraped_count = 0

                    update_scrape_status(db, f"✅ Session active", user_id, extra={
                        'is_running': True,
                        'total_kols': total_kols,
                        'scraped_count': scraped_count,
                        'current_kol': None,
                        'last_start_at': sync_time.isoformat()
                    })

                    consecutive_zeros = 0
                    # Mutable counter shared with scrape_profile to track total searches
                    search_counter = [0]
                    kol_timings = {}  # {name: {started_at, elapsed_s, posts}}
                    for idx, (kol_id, name, url) in enumerate(kols, start=1):
                        try:
                            kol_start = datetime.now(timezone.utc)
                            kol_timings[name] = {'started_at': kol_start.isoformat(), 'elapsed_s': None, 'posts': None}
                            update_scrape_status(db, f"Scraping {name}...", user_id, extra={
                                'is_running': True,
                                'total_kols': total_kols,
                                'scraped_count': scraped_count,
                                'current_kol': name,
                                'kol_timings': kol_timings
                            })

                            # Create a fresh page for each KOL to avoid session poisoning
                            kol_page = await context.new_page()
                            result = await asyncio.wait_for(
                                scrape_profile(kol_page, kol_id, name, url, db, sync_time, user_id=user_id, search_counter=search_counter),
                                timeout=600
                            )
                            await kol_page.close()

                            # Handle rate limiting / session degradation
                            if result == "rate_limited" or result == "session_degraded":
                                log_print(f"  🔄 Session degraded on {name}, rotating context quickly and moving to next...", user_id=user_id)
                                await context.close()
                                # No more 120s retry — it wastes time on IP blocks. 
                                # Just rotate and keep going with the next KOL.
                                context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
                                await context.add_cookies([
                                    {'name': 'auth_token', 'value': user_auth, 'domain': '.x.com', 'path': '/'},
                                    {'name': 'ct0', 'value': user_ct0, 'domain': '.x.com', 'path': '/'}
                                ])
                                consecutive_zeros = 0
                            elif result is True:
                                consecutive_zeros = 0
                            else:
                                consecutive_zeros += 1

                            # If 3+ consecutive KOLs got 0 posts, rotate context proactively
                            if consecutive_zeros >= 3:
                                log_print(f"  🔄 {consecutive_zeros} consecutive KOLs with 0 posts — rotating browser context...", user_id=user_id)
                                await context.close()
                                await asyncio.sleep(30)
                                context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
                                await context.add_cookies([
                                    {'name': 'auth_token', 'value': user_auth, 'domain': '.x.com', 'path': '/'},
                                    {'name': 'ct0', 'value': user_ct0, 'domain': '.x.com', 'path': '/'}
                                ])
                                consecutive_zeros = 0

                            scraped_count = idx
                            kol_elapsed = (datetime.now(timezone.utc) - kol_start).total_seconds()
                            kol_timings[name] = {'started_at': kol_start.isoformat(), 'elapsed_s': round(kol_elapsed, 1), 'posts': None}
                            update_scrape_status(db, f"Finished {name}", user_id, extra={
                                'is_running': True,
                                'total_kols': total_kols,
                                'scraped_count': scraped_count,
                                'current_kol': name,
                                'kol_timings': kol_timings
                            })
                        except asyncio.TimeoutError:
                            log_print(f"  ⏰ Timeout scraping {name} (600s), skipping...", user_id=user_id)
                            scraped_count = idx
                            kol_timings[name] = {'started_at': kol_start.isoformat(), 'elapsed_s': round((datetime.now(timezone.utc) - kol_start).total_seconds(), 1), 'posts': None, 'error': 'timeout'}
                            update_scrape_status(db, f"Timeout {name}", user_id, extra={
                                'is_running': True, 'total_kols': total_kols,
                                'scraped_count': scraped_count, 'current_kol': name,
                                'kol_timings': kol_timings
                            })
                            cur2.execute("UPDATE kols SET updated_at = %s WHERE id = %s", (sync_time, kol_id))
                            db.commit()
                            try:
                                await kol_page.close()
                            except:
                                pass
                        except Exception as e:
                            log_print(f"  ❌ Error scraping {name}: {e}", user_id=user_id)
                            scraped_count = idx
                            kol_timings[name] = {'started_at': kol_start.isoformat(), 'elapsed_s': round((datetime.now(timezone.utc) - kol_start).total_seconds(), 1), 'posts': None, 'error': str(e)[:100]}
                            update_scrape_status(db, f"Error {name}", user_id, extra={
                                'is_running': True, 'total_kols': total_kols,
                                'scraped_count': scraped_count, 'current_kol': name,
                                'kol_timings': kol_timings
                            })
                            cur2.execute("UPDATE kols SET updated_at = %s WHERE id = %s", (sync_time, kol_id))
                            db.commit()
                            try:
                                await kol_page.close()
                            except:
                                pass
                        # Progressive inter-KOL delay: increases as more searches accumulate
                        total_searches = search_counter[0]
                        if total_searches > 30:
                            kol_delay = random.randint(40, 60)
                        elif total_searches > 20:
                            kol_delay = random.randint(25, 40)
                        elif total_searches > 10:
                            kol_delay = random.randint(15, 25)
                        else:
                            kol_delay = random.randint(10, 15)
                        log_print(f"  ⏸️  Inter-KOL cooldown: {kol_delay}s (total searches so far: {total_searches})", user_id=user_id)
                        await asyncio.sleep(kol_delay)
                except Exception as e:
                    log_print(f"❌ User {user_id}: Critical session error: {e}", user_id=user_id)
                    update_scrape_status(db, f"❌ Critical error: {e}", user_id)
                
                await context.close()
                update_scrape_status(db, f"🏁 Scrape cycle complete for {len(kols)} KOLs.", user_id, extra={
                    'is_running': False,
                    'total_kols': len(kols),
                    'scraped_count': scraped_count,
                    'current_kol': None
                })
                log_print(f"--- Finished Scrape for User ID: {user_id} ---", user_id=user_id)
        await browser.close()
    finally:
        release_db(db)

def make_newposts_status_key(user_id=None):
    env_suffix = os.getenv("ENVIRONMENT_NAME", "Local").replace(" ", "_").lower()
    base = "twitter_newposts_status"
    if env_suffix:
        base = f"{base}_{env_suffix}"
    if user_id:
        base = f"{base}_{user_id}"
    return base

def update_newposts_status(db, message, user_id=None, extra=None):
    """Update the new posts scrape status in system_status table."""
    try:
        cur = db.cursor()
        key = make_newposts_status_key(user_id)
        cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
        row = cur.fetchone()
        status = row[0] if row else {}
        status['current_activity'] = message
        if extra:
            status.update(extra)
        logs = status.get('logs', [])
        if not logs or logs[-1] != f"[{datetime.now().strftime('%H:%M:%S')}] {message}":
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            status['logs'] = logs[-50:]
        cur.execute("""
            INSERT INTO system_status (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(status)))
        db.commit()
    except Exception as e:
        print(f"⚠️ Failed to update new posts status: {e}")


async def scrape_newposts_profile(page, kol_id, name, url, db, sync_time, cutoff_time, user_id=None):
    """Quick scrape: only find posts within the last 30 minutes. Stop at first old post."""
    start_ts = datetime.now(timezone.utc)
    username = get_twitter_username(url)
    if not username:
        log_print(f"  ⚠️ Could not extract username from {url}", user_id=user_id)
        return []

    log_print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔎 Quick scan {name} (@{username}) for posts since {cutoff_time.strftime('%H:%M')}", user_id=user_id)

    today = sync_time.date()
    tomorrow = today + timedelta(days=1)
    search_url = f"https://x.com/search?q=from%3A{username}%20since%3A{today.isoformat()}%20until%3A{tomorrow.isoformat()}&src=typed_query&f=live"

    # Longer pre-navigation pause to avoid rate limits on search
    await page.wait_for_timeout(random.randint(2000, 4000))
    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

    try:
        await page.wait_for_selector(
            'article[data-testid="tweet"], [data-testid="emptyState"]',
            timeout=12000
        )
    except:
        content = await page.content()
        content_lower = content.lower()
        if "rate limit" in content_lower or "something went wrong" in content_lower:
            log_print(f"  ⚠️ Rate limited for {name}, will retry after cooldown", user_id=user_id)
            return "rate_limited"
        # Could be slow page load, not necessarily rate limit
        page_text = await page.inner_text('body') if await page.query_selector('body') else ''
        if 'something went wrong' in page_text.lower():
            log_print(f"  ⚠️ Error page for {name}", user_id=user_id)
            return "rate_limited"
    await page.wait_for_timeout(1000)

    empty = await page.query_selector('[data-testid="emptyState"]')
    if empty:
        log_print(f"  🧭 {name}: no posts today", user_id=user_id)
        return []

    new_posts = []
    seen_ids = set()
    stale = 0
    last_count = 0
    hit_old_post = False

    for _ in range(50):  # limited scrolling for quick scan
        articles = await page.query_selector_all('article[data-testid="tweet"]')
        for tweet in articles:
            link = await tweet.query_selector('a[href*="/status/"]')
            if not link:
                continue
            href = await link.get_attribute('href')
            if not href:
                continue
            tid = href.split('/')[-1]
            post_id = f"tw_{tid}"
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            time_el = await tweet.query_selector('time')
            posted_at = await time_el.get_attribute('datetime') if time_el else None
            if not posted_at:
                continue

            # Check if this post is within our 30-minute window
            try:
                post_time = datetime.fromisoformat(posted_at.replace('Z', '+00:00'))
            except:
                continue

            if post_time < cutoff_time:
                # First post older than 30 minutes - stop this KOL
                log_print(f"  ⏹️  {name}: hit post from {post_time.strftime('%H:%M')} (older than cutoff {cutoff_time.strftime('%H:%M')}), stopping", user_id=user_id)
                hit_old_post = True
                break

            # Extract engagement metrics (same as full scrape)
            likes = '0'; reposts = '0'; replies = '0'; bookmarks = '0'; views = '0'
            group = await tweet.query_selector('[role="group"]')
            if group:
                aria = await group.get_attribute('aria-label')
                if aria:
                    replies_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+repl(?:y|ies)', aria, re.I)
                    reposts_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+repost(?:s)?', aria, re.I)
                    likes_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+like(?:s)?', aria, re.I)
                    bookmarks_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+bookmark(?:s)?', aria, re.I)
                    views_match = re.search(r'([\d.,]+(?:[KMkm]?))\s+view(?:s)?', aria, re.I)
                    if replies_match: replies = replies_match.group(1)
                    if reposts_match: reposts = reposts_match.group(1)
                    if likes_match: likes = likes_match.group(1)
                    if bookmarks_match: bookmarks = bookmarks_match.group(1)
                    if views_match: views = views_match.group(1)
                else:
                    # Fallback: button aria-labels
                    btn_map = {
                        'reply': ('replies', r'([\d.,]+[KMkm]?)'),
                        'retweet': ('reposts', r'([\d.,]+[KMkm]?)'),
                        'like': ('likes', r'([\d.,]+[KMkm]?)'),
                        'bookmark': ('bookmarks', r'([\d.,]+[KMkm]?)'),
                    }
                    for testid, (metric, pat) in btn_map.items():
                        btn = await group.query_selector(f'button[data-testid="{testid}"]')
                        if btn:
                            btn_aria = await btn.get_attribute('aria-label') or ''
                            m = re.search(pat, btn_aria)
                            if m:
                                val = m.group(1)
                                if testid == 'reply': replies = val
                                elif testid == 'retweet': reposts = val
                                elif testid == 'like': likes = val
                                elif testid == 'bookmark': bookmarks = val

            if views == '0':
                views_el = await tweet.query_selector('a[href*="/analytics"]')
                if views_el:
                    views_aria = await views_el.get_attribute('aria-label') or ''
                    views_m = re.search(r'([\d.,]+[KMkm]?)', views_aria)
                    if views_m:
                        views = views_m.group(1)
                if views == '0':
                    views_span = await tweet.query_selector('a[href*="/analytics"] span span')
                    if views_span:
                        views_text = (await views_span.inner_text()).strip()
                        if views_text and views_text != '0':
                            views = views_text

            tweet_text_el = await tweet.query_selector('div[data-testid="tweetText"]')
            tweet_text = await tweet_text_el.inner_text() if tweet_text_el else ''
            tweet_url = "https://x.com" + href

            post_data = {
                'post_id': post_id,
                'url': tweet_url,
                'content': tweet_text,
                'posted_at': posted_at,
                'likes': parse_count(likes),
                'reposts': parse_count(reposts),
                'comments': parse_count(replies),
                'bookmarks': parse_count(bookmarks),
                'views': parse_count(views)
            }
            new_posts.append(post_data)

        if hit_old_post:
            break

        if len(new_posts) == last_count:
            stale += 1
        else:
            stale = 0
        last_count = len(new_posts)

        if stale >= 3:
            break

        await page.evaluate("window.scrollBy(0, 1500)")
        await page.wait_for_timeout(random.randint(700, 1200))

    # Save new posts to DB
    if new_posts:
        cur = db.cursor()
        inserted = 0
        for item in new_posts:
            try:
                cur.execute("""
                    INSERT INTO twitter_posts (
                        kol_id, post_id, content, likes, reposts, comments, bookmarks, views, post_url, posted_at,
                        first_captured_at, captured_at,
                        last_likes, last_reposts, last_comments, last_bookmarks, last_views
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (post_id) DO UPDATE SET
                        likes = GREATEST(EXCLUDED.likes, twitter_posts.likes),
                        reposts = GREATEST(EXCLUDED.reposts, twitter_posts.reposts),
                        comments = GREATEST(EXCLUDED.comments, twitter_posts.comments),
                        bookmarks = GREATEST(EXCLUDED.bookmarks, twitter_posts.bookmarks),
                        views = GREATEST(EXCLUDED.views, twitter_posts.views),
                        captured_at = EXCLUDED.captured_at
                """, (
                    kol_id, item['post_id'], item['content'], item['likes'], item['reposts'], item['comments'], item['bookmarks'], item['views'],
                    item['url'], item['posted_at'], sync_time, sync_time,
                    item['likes'], item['reposts'], item['comments'], item['bookmarks'], item['views']
                ))
                inserted += 1
            except Exception:
                pass
        cur.execute("UPDATE kols SET updated_at = %s WHERE id = %s", (sync_time, kol_id))
        db.commit()
        log_print(f"  ✅ {name}: {inserted} new posts saved", user_id=user_id)

    elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
    log_print(f"  ✅ Quick scan {name} done in {elapsed:.1f}s: {len(new_posts)} posts within window", user_id=user_id)
    return new_posts


async def main_newposts():
    """Quick scrape mode: only find posts within the last 30 minutes for each KOL."""
    db = get_db()
    sync_time = datetime.now(timezone.utc)
    cutoff_time = sync_time - timedelta(minutes=30)
    all_new_posts = []

    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
        users = [str(r['user_id']) for r in cur.fetchall()]

        limit_users_env = os.getenv("LIMIT_TO_USER_IDS")
        limit_user = os.getenv("LIMIT_TO_USER_ID")
        target_users = None
        if limit_users_env:
            target_users = [u.strip() for u in limit_users_env.split(",") if u.strip()]
        elif limit_user:
            target_users = [limit_user]
        if target_users:
            filtered = [u for u in users if u in target_users]
            if not filtered:
                print(f"⚠️ No active KOLs found for specified users. Skipping new posts scrape.")
                return
            users = filtered

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=HEADLESS, args=['--no-sandbox'])

            for user_id in users:
                log_print(f"--- Starting New Posts Scan for User ID: {user_id} ---", user_id=user_id)

                cur.execute("SELECT twitter_auth_token, twitter_ct0 FROM user_configs WHERE user_id = %s", (user_id,))
                config_row = cur.fetchone()
                if not config_row or not config_row.get('twitter_auth_token'):
                    log_print(f"⚠️ User {user_id}: No X cookies configured. Skipping.", user_id=user_id)
                    continue

                user_auth = config_row['twitter_auth_token']
                user_ct0 = config_row['twitter_ct0']

                context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
                await context.add_cookies([
                    {'name': 'auth_token', 'value': user_auth, 'domain': '.x.com', 'path': '/'},
                    {'name': 'ct0', 'value': user_ct0, 'domain': '.x.com', 'path': '/'}
                ])

                page = await context.new_page()
                try:
                    await page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
                    if "login" in page.url:
                        log_print(f"❌ User {user_id}: Twitter/X login failed!", user_id=user_id)
                        update_newposts_status(db, f"❌ Login failed", user_id)
                        await context.close()
                        continue
                    log_print(f"✅ User {user_id}: Login OK", user_id=user_id)
                    await page.close()

                    cur2 = db.cursor()
                    cur2.execute("""
                        SELECT k.id, k.name, k.twitter_url
                        FROM kols k
                        WHERE k.status = 'active' AND k.user_id = %s
                        ORDER BY k.name
                    """, (user_id,))
                    kols = cur2.fetchall()
                    total_kols = len(kols)
                    scraped_count = 0
                    user_new_posts = []

                    update_newposts_status(db, f"Scanning {total_kols} KOLs for new posts...", user_id, extra={
                        'is_running': True,
                        'total_kols': total_kols,
                        'scraped_count': 0,
                        'current_kol': None,
                        'last_start_at': sync_time.isoformat(),
                        'cutoff_time': cutoff_time.isoformat()
                    })

                    consecutive_rate_limits = 0
                    for idx, (kol_id, name, url) in enumerate(kols, start=1):
                        try:
                            update_newposts_status(db, f"Scanning {name}...", user_id, extra={
                                'is_running': True,
                                'total_kols': total_kols,
                                'scraped_count': scraped_count,
                                'current_kol': name
                            })

                            kol_page = await context.new_page()
                            found = await asyncio.wait_for(
                                scrape_newposts_profile(kol_page, kol_id, name, url, db, sync_time, cutoff_time, user_id=user_id),
                                timeout=120
                            )
                            await kol_page.close()

                            # Handle rate limiting with context rotation
                            if found == "rate_limited":
                                consecutive_rate_limits += 1
                                if consecutive_rate_limits >= 3:
                                    log_print(f"  🔄 {consecutive_rate_limits} consecutive rate limits — rotating context and cooling down 60s...", user_id=user_id)
                                    await context.close()
                                    await asyncio.sleep(60)
                                    context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
                                    await context.add_cookies([
                                        {'name': 'auth_token', 'value': user_auth, 'domain': '.x.com', 'path': '/'},
                                        {'name': 'ct0', 'value': user_ct0, 'domain': '.x.com', 'path': '/'}
                                    ])
                                    consecutive_rate_limits = 0
                                else:
                                    await asyncio.sleep(random.randint(15, 25))
                                found = []
                            else:
                                consecutive_rate_limits = 0

                            for post in found:
                                post['kol_name'] = name
                            user_new_posts.extend(found)

                            scraped_count = idx
                            update_newposts_status(db, f"Finished {name} ({len(found)} new)", user_id, extra={
                                'is_running': True,
                                'total_kols': total_kols,
                                'scraped_count': scraped_count,
                                'current_kol': None
                            })

                        except asyncio.TimeoutError:
                            log_print(f"  ⏰ Timeout scanning {name}, skipping", user_id=user_id)
                            scraped_count = idx
                            try: await kol_page.close()
                            except: pass
                        except Exception as e:
                            log_print(f"  ❌ Error scanning {name}: {e}", user_id=user_id)
                            scraped_count = idx
                            try: await kol_page.close()
                            except: pass

                        # Inter-KOL delay to respect rate limits
                        await asyncio.sleep(random.randint(8, 15))

                except Exception as e:
                    log_print(f"❌ User {user_id}: Critical error: {e}", user_id=user_id)
                    update_newposts_status(db, f"❌ Error: {e}", user_id)

                await context.close()

                # Store results summary in status
                update_newposts_status(db, f"Scan complete: {len(user_new_posts)} new posts from {total_kols} KOLs", user_id, extra={
                    'is_running': False,
                    'total_kols': total_kols,
                    'scraped_count': scraped_count,
                    'current_kol': None,
                    'finished_at': datetime.now(timezone.utc).isoformat(),
                    'new_posts_count': len(user_new_posts),
                    'new_posts': [
                        {
                            'kol_name': p['kol_name'],
                            'post_id': p['post_id'],
                            'content': (p['content'] or '')[:200],
                            'posted_at': p['posted_at'],
                            'scraped_at': sync_time.isoformat(),
                            'post_url': p['url'],
                            'likes': p['likes'],
                            'reposts': p['reposts'],
                            'comments': p['comments'],
                            'views': p['views'],
                            'bookmarks': p['bookmarks']
                        } for p in user_new_posts
                    ]
                })
                all_new_posts.extend(user_new_posts)
                log_print(f"--- Finished New Posts Scan for User ID: {user_id}: {len(user_new_posts)} new posts ---", user_id=user_id)

                # Push to Discord directly after storing results
                try:
                    from discord_push import build_newposts_embeds, send_embeds
                    cur_wh = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    cur_wh.execute("SELECT discord_webhook_posts FROM user_configs WHERE user_id = %s", (user_id,))
                    wh_row = cur_wh.fetchone()
                    webhook_url = wh_row.get('discord_webhook_posts') if wh_row else None
                    if webhook_url:
                        embeds = build_newposts_embeds(user_id)
                        if embeds:
                            await send_embeds(webhook_url, embeds)
                            log_print(f"  📤 Pushed {len(embeds)} new post(s) to Discord for user {user_id}", user_id=user_id)
                        else:
                            await send_embeds(webhook_url, [{
                                "title": "📝 New Posts Scan Complete",
                                "description": "No new posts found in the past 30 minutes.",
                                "color": 0x2C2F33,
                                "footer": {"text": "New Posts Scan (30-min window)"}
                            }])
                            log_print(f"  📤 No new posts, sent empty notification to Discord for user {user_id}", user_id=user_id)
                    else:
                        log_print(f"  ⚠️ No discord_webhook_posts configured for user {user_id}", user_id=user_id)
                except Exception as e:
                    log_print(f"  ❌ Discord push error for user {user_id}: {e}", user_id=user_id)

            await browser.close()
    finally:
        release_db(db)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "newposts":
        asyncio.run(main_newposts())
    else:
        asyncio.run(main())
