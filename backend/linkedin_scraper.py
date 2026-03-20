"""
LinkedIn KOL Monitor - Scrapes LinkedIn profiles for posts, interactions, connections, metrics.
Uses Playwright with authenticated cookies.
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg2
from playwright.async_api import async_playwright

# Config
DB_DSN = "dbname=kol_monitor host=/tmp"
CREDENTIALS_PATH = "/data/.openclaw/workspace/.credentials/linkedin.json"
HEADLESS = True
SLOW_MO = 2000  # ms between actions to avoid detection

def get_db():
    return psycopg2.connect(DB_DSN)

def load_cookies():
    with open(CREDENTIALS_PATH) as f:
        creds = json.load(f)
    return creds

def get_kols(db):
    cur = db.cursor()
    cur.execute("SELECT id, name, linkedin_url FROM kols WHERE status='active' AND linkedin_url IS NOT NULL ORDER BY id")
    return cur.fetchall()

async def scrape_profile(page, kol_id, name, url, db):
    """Scrape a single LinkedIn profile for posts and metrics."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scraping: {name} - {url}")
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Check if we're blocked or need to login
        page_text = await page.content()
        if "authwall" in page_text.lower() or "sign in" in page_text.lower():
            print(f"  ⚠️  Auth wall detected for {name}, skipping...")
            return False
        
        # --- Scrape Profile Metrics ---
        metrics = {}
        
        # Try to get follower count
        try:
            followers_el = await page.query_selector('span.t-bold:near(:text("followers"))')
            if followers_el:
                followers_text = await followers_el.text_content()
                metrics['followers'] = parse_count(followers_text.strip())
        except:
            pass
        
        # Try to get connections count
        try:
            connections_el = await page.query_selector('span.t-bold:near(:text("connections"))')
            if connections_el:
                connections_text = await connections_el.text_content()
                metrics['connections'] = parse_count(connections_text.strip())
        except:
            pass
        
        # Save metrics
        cur = db.cursor()
        cur.execute("""
            INSERT INTO kol_metrics (kol_id, platform, followers_count, connections_count)
            VALUES (%s, 'linkedin', %s, %s)
        """, (kol_id, metrics.get('followers'), metrics.get('connections')))
        
        print(f"  📊 Metrics: {metrics}")
        
        # --- Scrape Recent Posts ---
        # Navigate to activity page
        activity_url = url.rstrip('/') + '/recent-activity/all/'
        await page.goto(activity_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Scroll to load more posts
        for _ in range(2):
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(1500)
        
        # Extract posts
        post_elements = await page.query_selector_all('div.feed-shared-update-v2')
        post_count = 0
        
        for post_el in post_elements[:10]:  # Max 10 recent posts
            try:
                # Get post content
                content_el = await post_el.query_selector('div.feed-shared-update-v2__description')
                content = ""
                if content_el:
                    content = (await content_el.text_content()).strip()
                
                if not content:
                    content_el = await post_el.query_selector('span.break-words')
                    if content_el:
                        content = (await content_el.text_content()).strip()
                
                if not content:
                    continue
                
                # Get engagement numbers
                likes = 0
                comments = 0
                
                try:
                    social_counts = await post_el.query_selector('ul.social-details-social-counts')
                    if social_counts:
                        counts_text = await social_counts.text_content()
                        like_match = re.search(r'(\d+)\s*(like|reaction)', counts_text, re.I)
                        comment_match = re.search(r'(\d+)\s*comment', counts_text, re.I)
                        if like_match:
                            likes = int(like_match.group(1))
                        if comment_match:
                            comments = int(comment_match.group(1))
                except:
                    pass
                
                # Generate a pseudo post_id from content hash
                post_id = f"li_{kol_id}_{hash(content[:100]) % 10**8}"
                
                cur.execute("""
                    INSERT INTO linkedin_posts (kol_id, post_id, content, likes, comments)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (post_id) DO UPDATE SET
                        likes = EXCLUDED.likes,
                        comments = EXCLUDED.comments,
                        captured_at = NOW()
                """, (kol_id, post_id, content[:2000], likes, comments))
                
                post_count += 1
            except Exception as e:
                print(f"  ⚠️  Error parsing post: {e}")
                continue
        
        db.commit()
        print(f"  ✅ Scraped {post_count} posts for {name}")
        return True
        
    except Exception as e:
        print(f"  ❌ Error scraping {name}: {e}")
        db.rollback()
        return False

def parse_count(text):
    """Parse '1.2K' or '500' style counts."""
    text = text.replace(',', '').strip()
    multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}
    match = re.match(r'([\d.]+)\s*([kmb])?', text.lower())
    if match:
        num = float(match.group(1))
        suffix = match.group(2)
        if suffix and suffix in multipliers:
            num *= multipliers[suffix]
        return int(num)
    return None

async def main():
    creds = load_cookies()
    db = get_db()
    kols = get_kols(db)
    
    print(f"🚀 LinkedIn KOL Monitor - Scraping {len(kols)} KOLs")
    print(f"⏰ Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # Set LinkedIn cookies
        await context.add_cookies([
            {
                'name': 'li_at',
                'value': creds['li_at'],
                'domain': '.linkedin.com',
                'path': '/',
                'httpOnly': True,
                'secure': True,
            },
            {
                'name': 'JSESSIONID',
                'value': creds['JSESSIONID'],
                'domain': '.linkedin.com',
                'path': '/',
                'httpOnly': False,
                'secure': True,
            }
        ])
        
        page = await context.new_page()
        
        # Verify login
        await page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        
        if 'login' in page.url or 'authwall' in page.url:
            print("❌ LinkedIn login failed! Cookies may be expired.")
            await browser.close()
            db.close()
            sys.exit(1)
        
        print("✅ LinkedIn login successful!")
        
        success = 0
        failed = 0
        
        for kol_id, name, url in kols:
            result = await scrape_profile(page, kol_id, name, url, db)
            if result:
                success += 1
            else:
                failed += 1
            
            # Random delay between profiles
            delay = SLOW_MO / 1000 + (hash(name) % 3)
            await page.wait_for_timeout(int(delay * 1000))
        
        await browser.close()
    
    db.close()
    print(f"\n📊 Done! Success: {success}, Failed: {failed}")

if __name__ == "__main__":
    asyncio.run(main())
