"""
Twitter/X KOL Monitor - Scrapes Twitter profiles using Playwright with cookies.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

import psycopg2
from playwright.async_api import async_playwright
from config import DB_DSN, TWITTER_AUTH_TOKEN, TWITTER_CT0, HEADLESS, SLOW_MO

def get_db():
    return psycopg2.connect(DB_DSN)

def get_kols(db):
    cur = db.cursor()
    cur.execute("SELECT id, name, twitter_url FROM kols WHERE status='active' AND twitter_url IS NOT NULL ORDER BY id")
    return cur.fetchall()

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
        await page.wait_for_timeout(3000)
        
        # If we want reposters, we need to click the reposts count
        if interaction_type == "reposts":
             try:
                 # Try to find and click the reposts button/link
                 repost_link = await page.query_selector('a[href$="/retweets"]')
                 if repost_link:
                     await repost_link.click()
                     await page.wait_for_timeout(3000)
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
            await page.wait_for_timeout(random.randint(2000, 4000))

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

async def scrape_profile(page, kol_id, name, url, db):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping X: {name} - {url}")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        
        # Wait for the main react element to render or timeout
        try:
            await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=15000)
        except Exception:
            print(f"  ⚠️ Timeout waiting for primaryColumn, trying reload...")
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=15000)

        await page.wait_for_timeout(SLOW_MO)
        
        # Keep scrolling a bit to load the tweets (sometimes they are lazy loaded or we need to skip pinned tweets)
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(2000)
        
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
                INSERT INTO kol_metrics (kol_id, platform, followers_count, following_count)
                VALUES (%s, 'twitter', %s, %s)
            """, (kol_id, metrics.get('followers'), metrics.get('following')))
            print(f"  📊 Metrics: Followers: {metrics.get('followers')}, Following: {metrics.get('following')}")

        # --- Scrape Recent Tweets ---
        tweet_count = 0
        tweets = await page.query_selector_all('article[data-testid="tweet"]')
        processed_tweets = []

        for tweet in tweets[:15]:
            try:
                tweet_text_el = await tweet.query_selector('div[data-testid="tweetText"]')
                if not tweet_text_el: continue
                tweet_text = await tweet_text_el.inner_text()
                
                time_el = await tweet.query_selector('time')
                posted_at = await time_el.get_attribute('datetime') if time_el else None
                
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
                    INSERT INTO twitter_posts (kol_id, post_id, content, likes, reposts, comments, bookmarks, views, post_url, posted_at, captured_at, last_likes, last_reposts, last_comments, last_bookmarks, last_views)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s)
                    ON CONFLICT (post_id) DO UPDATE SET 
                        last_likes = twitter_posts.likes, 
                        last_reposts = twitter_posts.reposts, 
                        last_comments = twitter_posts.comments, 
                        last_bookmarks = twitter_posts.bookmarks, 
                        last_views = twitter_posts.views,
                        likes = EXCLUDED.likes, 
                        reposts = EXCLUDED.reposts, 
                        comments = EXCLUDED.comments, 
                        bookmarks = EXCLUDED.bookmarks, 
                        views = EXCLUDED.views, 
                        captured_at = NOW()
                    RETURNING id
                """, (kol_id, f"tw_{tweet_id}", tweet_text, parse_count(likes), parse_count(reposts), parse_count(replies), parse_count(bookmarks), parse_count(views), tweet_url, posted_at, parse_count(likes), parse_count(reposts), parse_count(replies), parse_count(bookmarks), parse_count(views)))
                
                db_post_id = cur.fetchone()[0]
                processed_tweets.append({'db_id': db_post_id, 'url': tweet_url, 'replies': parse_count(replies), 'reposts': parse_count(reposts)})
                tweet_count += 1
            except Exception as e:
                print(f"  ⚠️  Error parsing tweet for {name}: {e}")
                continue

        db.commit()
        print(f"  ✅ Scraped {tweet_count} tweets for @{get_twitter_username(url)}")
        
        # Now scrape detailed interactions if they are high
        for pt in processed_tweets:
            if pt['replies'] > 5:
                await scrape_post_interactions(page, db, pt['db_id'], pt['url'], "replies")
            if pt['reposts'] > 5:
                await scrape_post_interactions(page, db, pt['db_id'], pt['url'], "reposts")
        
        return True

    except Exception as e:
        print(f"  ❌ Error scraping {name}: {e}")
        db.rollback()
        return False

async def main():
    db = get_db()
    
    # Scrape by User isolation
    cur = db.cursor()
    cur.execute("SELECT DISTINCT user_id FROM kols WHERE status = 'active'")
    users = [r[0] for r in cur.fetchall()]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, args=['--no-sandbox'])
        
        for user_id in users:
            print(f"--- Starting Scrape for User ID: {user_id} ---")
            
            # Load user-specific cookies
            creds_path = f"/data/.openclaw/workspace/kol-monitor/credentials/twitter_{user_id}.json"
            if os.path.exists(creds_path):
                with open(creds_path) as f:
                    creds = json.load(f)
                    user_auth = creds['auth_token']
                    user_ct0 = creds['ct0']
            else:
                user_auth = TWITTER_AUTH_TOKEN
                user_ct0 = TWITTER_CT0

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
                    await context.close()
                    continue
                print(f"✅ User {user_id}: Twitter/X login successful!")

                # Filter KOLs by this user
                cur.execute("SELECT id, name, twitter_url FROM kols WHERE status = 'active' AND user_id = %s", (user_id,))
                kols = cur.fetchall()
                
                for kol_id, name, url in kols:
                    await scrape_profile(page, kol_id, name, url, db)
                    await asyncio.sleep(SLOW_MO / 1000)
            except Exception as e:
                print(f"❌ User {user_id}: Critical scrape error: {e}")
            
            await context.close()
            
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
