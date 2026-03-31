import asyncio
import os
import json
from datetime import datetime
import psycopg2
import psycopg2.extras
from playwright.async_api import async_playwright

from db import get_db, release_db
from config import HEADLESS, SLOW_MO


async def send_dm(page, handle, message):
    try:
        # Navigate to compose message
        await page.goto("https://x.com/messages/compose", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        
        # Type handle into search
        search_input = page.locator('[data-testid="searchPeople"]')
        await search_input.fill(handle)
        await page.wait_for_timeout(2000)
        
        # Click the first matching user result
        user_result = page.locator(f'[data-testid="TypeaheadUser"]').first
        await user_result.click()
        await page.wait_for_timeout(1000)
        
        # Click Next
        next_btn = page.locator('[data-testid="nextButton"]')
        await next_btn.click()
        await page.wait_for_timeout(2000)
        
        # Type message
        composer = page.locator('[data-testid="dmComposerTextInput"]')
        await composer.fill(message)
        await page.wait_for_timeout(1000)
        
        # Click Send
        send_btn = page.locator('[data-testid="dmComposerSendButton"]')
        await send_btn.click()
        await page.wait_for_timeout(2000)
        return True
    except Exception as e:
        print(f"❌ Failed to send DM to {handle}: {e}")
        return False

async def main():
    print(f"--- Running DM Scheduler ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ---")
    current_day = datetime.now().strftime("%A")  # e.g., 'Monday'
    current_time_str = datetime.now().strftime("%H:%M")
    
    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Fetch KOLs scheduled for today whose time has passed, but haven't been sent a DM today
        # dm_day supports comma-separated days (e.g. "Tuesday,Sunday")
        cur.execute("""
            SELECT k.*, k.user_id as u_id
            FROM kols k
            WHERE k.status = 'active'
            AND k.dm_text IS NOT NULL AND k.dm_text != ''
            AND k.dm_day IS NOT NULL AND k.dm_day != ''
            AND k.dm_time IS NOT NULL AND k.dm_time != ''
            AND k.dm_time <= %s
            AND k.id NOT IN (
                SELECT kol_id FROM dm_logs
                WHERE DATE(sent_at) = CURRENT_DATE AND status = 'sent' AND direction = 'outbound'
            )
        """, (current_time_str,))

        # Filter: current day must be in the KOL's comma-separated dm_day list
        all_pending = cur.fetchall()
        pending_dms = [
            dm for dm in all_pending
            if current_day in [d.strip() for d in (dm.get('dm_day') or '').split(',')]
        ]
        
        if not pending_dms:
            print("✅ No pending scheduled DMs for this time window.")
            return

        print(f"📨 Found {len(pending_dms)} DMs to send today.")
        
        # Group by user_id to reuse Playwright context per user
        dms_by_user = {}
        for dm in pending_dms:
            uid = str(dm['u_id'])
            if uid not in dms_by_user: dms_by_user[uid] = []
            dms_by_user[uid].append(dm)
            
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=HEADLESS, args=['--no-sandbox'])
            
            for user_id, user_dms in dms_by_user.items():
                print(f"--- Sending DMs for User ID: {user_id} ---")
                
                # Fetch X cookies from user_configs table
                cur.execute("""
                    SELECT twitter_auth_token, twitter_ct0 
                    FROM user_configs WHERE user_id = %s
                """, (user_id,))
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
                        print(f"❌ User {user_id}: Twitter/X login failed! Cannot send DMs.")
                        await context.close()
                        continue
                        
                    # Send DMs for this user
                    for idx, kol in enumerate(user_dms):
                        handle = kol['twitter_url'].split('/')[-1] if kol['twitter_url'] else kol['name']
                        print(f"  ✉️ Sending DM to {handle}...")
                        
                        success = await send_dm(page, handle, kol['dm_text'])
                        
                        # Log attempt
                        cur.execute("""
                            INSERT INTO dm_logs (kol_id, platform, direction, content, status, sent_at)
                            VALUES (%s, 'twitter', 'outbound', %s, %s, NOW())
                        """, (kol['id'], kol['dm_text'], 'sent' if success else 'failed'))
                        db.commit()
                        
                        if success:
                            print(f"  ✅ Sent successfully.")
                        
                        if idx < len(user_dms) - 1:
                            await asyncio.sleep(5)  # Pause between DMs
                except Exception as e:
                    print(f"❌ User {user_id}: Critical DM error: {e}")
                
                await context.close()
            
            await browser.close()
    finally:
        release_db(db)
    print("🏁 Scheduled DMs check complete.")

if __name__ == "__main__":
    asyncio.run(main())
