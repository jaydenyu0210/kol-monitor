"""
Twitter/X KOL Monitor - Scrapes Twitter profiles using Playwright with cookies.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import psycopg2
import psycopg2.extras
from playwright.async_api import async_playwright
from db import get_db, release_db
from config import HEADLESS, SLOW_MO

def get_kols(db):
    cur = db.cursor()
    cur.execute("SELECT id, name, twitter_url FROM kols WHERE status='active' AND twitter_url IS NOT NULL ORDER BY id")
    return cur.fetchall()

def update_scrape_status(db, message, user_id=None):
    """Update the current activity in the system_status table, partitioned by user if provided."""
    try:
        cur = db.cursor()
        key = 'twitter_scraper_status'
        if user_id:
            key = f'twitter_scraper_status_{user_id}'
            
        cur.execute("SELECT value FROM system_status WHERE key = %s", (key,))
        row = cur.fetchone()
        status = row[0] if row else {}
        
        status['current_activity'] = message
        
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

async def scrape_profile(page, kol_id, name, url, db, sync_time, user_id=None):
    msg = f"Scraping {name} (@{get_twitter_username(url)})"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    update_scrape_status(db, msg, user_id=user_id)
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        # Wait for the main react element to render or timeout
        try:
            await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=8000)
        except Exception:
            current_url = page.url
            if "login" in current_url.lower():
                print(f"  ❌ SESSION EXPIRED: Redirected to login page. Skipping profile.")
                return False
            
            content = await page.content()
            if "rate limit" in content.lower() or "something went wrong" in content.lower():
                print(f"  ⚠️ RATE LIMITED: Twitter is blocking requests. Sleeping for a while...")
                await asyncio.sleep(30)
                return False

            print(f"  ⚠️ Timeout waiting for primaryColumn at {current_url}, trying reload...")
            await page.reload(wait_until="domcontentloaded", timeout=15000)
            try:
                await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=12000)
            except:
                print(f"  ❌ FAILED: Still no primaryColumn after reload at {page.url}")
                return False

        # --- Poke Scroll to trigger lazy loading ---
        print(f"  ⏳ Poking page to trigger lazy loading for {name}...")
        await page.evaluate("window.scrollBy(0, 300)")
        await page.wait_for_timeout(1000)
        await page.evaluate("window.scrollBy(0, -300)")
        await page.wait_for_timeout(500)

        # --- Initial Wait for Content ---
        print(f"  ⏳ Waiting for initial tweets to load for {name}...")
        try:
            # Wait for either a tweet or a cellInnerDiv which usually contains tweets/content
            await page.wait_for_selector('article[data-testid="tweet"], div[data-testid="cellInnerDiv"]', timeout=15000)
        except:
            print(f"  ⚠️ Warning: No content found after initial wait for {name}.")

        # Deep scroll to load more history
        print(f"  ⏳ Deep scrolling for {name}...")
        for i in range(10): # Back to 10 scrolls, smaller distance
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(800)
        
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
            print(f"  ⚠️  Could not parse metrics for {name}: {e}")

        cur = db.cursor()
        if metrics:
            cur.execute("""
                INSERT INTO kol_metrics (kol_id, platform, followers_count, following_count, captured_at)
                VALUES (%s, 'twitter', %s, %s, %s)
            """, (kol_id, metrics.get('followers'), metrics.get('following'), sync_time))
            print(f"  📊 Metrics: Followers: {metrics.get('followers')}, Following: {metrics.get('following')}")

        # --- Scrape Recent Tweets ---
        tweet_count = 0
        skipped_count = 0
        all_tweets = await page.query_selector_all('article[data-testid="tweet"]')
        processed_tweets = []
        
        print(f"  🔍 Found {len(all_tweets)} potential tweets. Processing with 7-day filter...")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)

        for tweet in all_tweets[:100]:
            try:
                tweet_text_el = await tweet.query_selector('div[data-testid="tweetText"]')
                if not tweet_text_el: continue
                tweet_text = await tweet_text_el.inner_text()
                time_el = await tweet.query_selector('time')
                posted_at = await time_el.get_attribute('datetime') if time_el else None
                
                if posted_at:
                    # Clean up Z and convert to UTC datetime
                    posted_dt = datetime.fromisoformat(posted_at.replace('Z', '+00:00'))
                    if posted_dt < cutoff_date:
                        # Skip old posts (likely pinned)
                        skipped_count += 1
                        continue
                
                tweet_id_el = await tweet.query_selector('a[href*="/status/"]')
                tweet_url = "https://x.com" + await tweet_id_el.get_attribute('href')
                tweet_id = tweet_url.split('/')[-1]

                likes = '0'
                reposts = '0'
                replies = '0'
                bookmarks = '0'
                views = '0'

                group = await tweet.query_selector('[role="group"]')
                if group:
                    aria = await group.get_attribute('aria-label')
                    if aria:
                        replies_match = re.search(r'([\d\.,]+(?:[KMkm]?))\s+replies', aria, re.I)
                        reposts_match = re.search(r'([\d\.,]+(?:[KMkm]?))\s+reposts', aria, re.I)
                        likes_match = re.search(r'([\d\.,]+(?:[KMkm]?))\s+likes', aria, re.I)
                        bookmarks_match = re.search(r'([\d\.,]+(?:[KMkm]?))\s+bookmarks', aria, re.I)
                        views_match = re.search(r'([\d\.,]+(?:[KMkm]?))\s+views', aria, re.I)
                        
                        if replies_match: replies = replies_match.group(1)
                        if reposts_match: reposts = reposts_match.group(1)
                        if likes_match: likes = likes_match.group(1)
                        if bookmarks_match: bookmarks = bookmarks_match.group(1)
                        if views_match: views = views_match.group(1)

                if views == '0':
                    views_el = await tweet.query_selector('a[href*="/analytics"]')
                    if views_el:
                        views = await views_el.get_attribute('aria-label') or '0'

                cur.execute("""
                    INSERT INTO twitter_posts (
                        kol_id, post_id, content, likes, reposts, comments, bookmarks, views, post_url, posted_at, 
                        first_captured_at, captured_at, 
                        last_likes, last_reposts, last_comments, last_bookmarks, last_views
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (post_id) DO UPDATE SET 
                        last_likes = CASE WHEN EXCLUDED.likes != twitter_posts.likes THEN twitter_posts.likes ELSE twitter_posts.last_likes END, 
                        last_reposts = CASE WHEN EXCLUDED.reposts != twitter_posts.reposts THEN twitter_posts.reposts ELSE twitter_posts.last_reposts END, 
                        last_comments = CASE WHEN EXCLUDED.comments != twitter_posts.comments THEN twitter_posts.comments ELSE twitter_posts.last_comments END, 
                        last_bookmarks = CASE WHEN EXCLUDED.bookmarks != twitter_posts.bookmarks THEN twitter_posts.bookmarks ELSE twitter_posts.last_bookmarks END, 
                        last_views = CASE WHEN EXCLUDED.views != twitter_posts.views THEN twitter_posts.views ELSE twitter_posts.last_views END,
                        likes = EXCLUDED.likes, 
                        reposts = EXCLUDED.reposts, 
                        comments = EXCLUDED.comments, 
                        bookmarks = EXCLUDED.bookmarks, 
                        views = EXCLUDED.views, 
                        captured_at = EXCLUDED.captured_at
                    RETURNING id
                """, (kol_id, f"tw_{tweet_id}", tweet_text, parse_count(likes), parse_count(reposts), parse_count(replies), parse_count(bookmarks), parse_count(views), tweet_url, posted_at, sync_time, sync_time, parse_count(likes), parse_count(reposts), parse_count(replies), parse_count(bookmarks), parse_count(views)))
                
                db_post_id = cur.fetchone()[0]
                processed_tweets.append({'db_id': db_post_id, 'url': tweet_url, 'replies': parse_count(replies), 'reposts': parse_count(reposts)})
                tweet_count += 1
            except Exception as e:
                print(f"  ⚠️  Error parsing tweet for {name}: {e}")
                continue

        # Count total stored for this KOL in the 7-day window for verification
        cur.execute("SELECT COUNT(*) FROM twitter_posts WHERE kol_id = %s AND (posted_at > %s OR (posted_at IS NULL AND captured_at > %s))", (kol_id, cutoff_date, cutoff_date))
        total_stored = cur.fetchone()[0]
        
        db.commit()
        print(f"  ✅ Finished @{get_twitter_username(url)}: {tweet_count} new/updated, {skipped_count} skipped. [Total 7d History: {total_stored} posts]")
        
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
        print(f"  ❌ Error scraping {name}: {e}")
        db.rollback()
        return False

async def main():
    db = get_db()
    sync_time = datetime.now(timezone.utc)
    try:
        # Scrape by User isolation
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
        users = [str(r['user_id']) for r in cur.fetchall()]
        
        # [NEW] Optional filter to only scrape a specific user (ideal for local development)
        limit_user = os.getenv("LIMIT_TO_USER_ID")
        if limit_user:
            if limit_user in users:
                users = [limit_user]
            else:
                print(f"⚠️ LIMIT_TO_USER_ID={limit_user} set but no active KOLs found for this user. Skipping scrape.")
                return
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=HEADLESS, args=['--no-sandbox'])
            
            for user_id in users:
                print(f"--- Starting Scrape for User ID: {user_id} ---")
                
                # Fetch X cookies from user_configs table
                cur.execute("SELECT twitter_auth_token, twitter_ct0 FROM user_configs WHERE user_id = %s", (user_id,))
                config_row = cur.fetchone()
                
                if not config_row or not config_row.get('twitter_auth_token'):
                    print(f"⚠️ User {user_id}: No X cookies configured. Skipping.")
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
                        print(f"❌ User {user_id}: Twitter/X login failed with cookies!")
                        update_scrape_status(db, f"❌ Login failed", user_id)
                        await context.close()
                        continue
                    print(f"✅ User {user_id}: Twitter/X login successful!")
                    update_scrape_status(db, f"✅ Session active", user_id)

                    # Filter KOLs by this user
                    cur2 = db.cursor()
                    cur2.execute("SELECT id, name, twitter_url FROM kols WHERE status = 'active' AND user_id = %s", (user_id,))
                    kols = cur2.fetchall()
                    
                    for kol_id, name, url in kols:
                        try:
                            update_scrape_status(db, f"Scraping {name}...", user_id)
                            await asyncio.wait_for(
                                scrape_profile(page, kol_id, name, url, db, sync_time, user_id=user_id),
                                timeout=60
                            )
                        except asyncio.TimeoutError:
                            print(f"  ⏰ Timeout scraping {name} (60s), skipping...")
                            cur2.execute("UPDATE kols SET updated_at = %s WHERE id = %s", (sync_time, kol_id))
                            db.commit()
                        except Exception as e:
                            print(f"  ❌ Error scraping {name}: {e}")
                            cur2.execute("UPDATE kols SET updated_at = %s WHERE id = %s", (sync_time, kol_id))
                            db.commit()
                        await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"❌ User {user_id}: Critical session error: {e}")
                    update_scrape_status(db, f"❌ Critical error: {e}", user_id)
                
                await context.close()
                update_scrape_status(db, f"🏁 Scrape cycle complete for {len(kols)} KOLs.", user_id)
                print(f"--- Finished Scrape for User ID: {user_id} ---")
        await browser.close()
    finally:
        release_db(db)

if __name__ == "__main__":
    asyncio.run(main())
