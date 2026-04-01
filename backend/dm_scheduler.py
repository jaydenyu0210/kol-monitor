import asyncio
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import psycopg2
import psycopg2.extras
from playwright.async_api import async_playwright

from db import get_db, release_db
from config import HEADLESS, SLOW_MO

def get_user_now(tz_name: str):
    """Return current datetime in the user's configured timezone (default: UTC)."""
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except ZoneInfoNotFoundError:
        print(f"⚠️ Unknown timezone '{tz_name}', falling back to UTC")
        tz = ZoneInfo("UTC")
    return datetime.now(tz)


async def wait_for_page_ready(page, label="page", timeout=30000):
    """Wait until the page loads past the X splash screen."""
    import time
    start = time.time()
    deadline = timeout / 1000
    while time.time() - start < deadline:
        # Check if real content has loaded (nav bar, main content, etc.)
        nav = page.locator('nav[role="navigation"], header[role="banner"], [data-testid="primaryColumn"], [data-testid="DmActivityContainer"]')
        if await nav.count() > 0:
            print(f"    [DM] ✅ {label} loaded successfully.")
            return True
        await page.wait_for_timeout(1000)

    print(f"    [DM] ⚠️ {label} did not load within {timeout/1000}s (may be rate limited).")
    return False


async def handle_passcode_overlay(page, passcode):
    """Handle the X encrypted DMs passcode overlay/mask if it appears."""
    try:
        await page.wait_for_timeout(2000)

        # Check for the mask overlay that blocks clicks
        mask = page.locator('[data-testid="mask"]')
        page_text = await page.content()
        has_passcode = "Enter Passcode" in page_text or "passcode" in page_text.lower() or "pin/recovery" in page.url
        has_mask = await mask.count() > 0

        if not has_passcode and not has_mask:
            return True  # No overlay

        if has_mask and not has_passcode:
            # Mask exists but no passcode text — try clicking it to dismiss
            print(f"    [DM] Mask overlay detected, clicking to dismiss...")
            try:
                await mask.click()
                await page.wait_for_timeout(1500)
            except:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1500)
            # Check if mask is gone
            if await mask.count() == 0:
                print(f"    [DM] ✅ Mask dismissed.")
                return True

        if has_passcode:
            if not passcode:
                print(f"    [DM] ⚠️ Passcode dialog detected but no passcode configured!")
                return False

            print(f"    [DM] Passcode dialog detected, entering passcode...")
            for digit in passcode:
                await page.keyboard.press(digit)
                await page.wait_for_timeout(300)
            await page.wait_for_timeout(3000)

            # Verify passcode was accepted
            new_text = await page.content()
            if "Enter Passcode" in new_text or "pin/recovery" in page.url:
                print(f"    [DM] ⚠️ Passcode may have failed")
                await page.screenshot(path="/tmp/dm_passcode_fail.png")
                return False

            print(f"    [DM] ✅ Passcode accepted!")

        # Final check: dismiss any remaining mask
        if await mask.count() > 0:
            print(f"    [DM] Mask still present after passcode, pressing Escape...")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1500)

        return True
    except Exception as e:
        print(f"    [DM] Passcode/mask handling error: {e}")
        return False


async def send_dm(page, handle, message, passcode=None):
    """
    Send a DM via X/Twitter using the messages UI flow:
    1. Navigate to /messages
    2. Handle passcode overlay
    3. Click the new message (compose) icon
    4. Search for the target username
    5. Select the user from results
    6. Click Next to open conversation
    7. Type message and press Enter to send
    """
    step = "init"
    try:
        # Step 1: Navigate to messages
        step = "messages_page"
        print(f"    [DM] Navigating to messages page...")
        await page.goto("https://x.com/messages", wait_until="domcontentloaded", timeout=30000)
        if not await wait_for_page_ready(page, "Messages page", timeout=25000):
            await page.screenshot(path=f"/tmp/dm_fail_{handle}_messages_load.png")
            print(f"    [DM] ❌ Messages page failed to load")
            return False
        print(f"    [DM] Messages page URL: {page.url}")

        # Step 2: Handle passcode/mask overlay
        step = "passcode"
        if not await handle_passcode_overlay(page, passcode):
            print(f"    [DM] ❌ Cannot proceed — passcode/mask issue. Set DM passcode in Settings.")
            return False

        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"/tmp/dm_debug_{handle}_after_passcode.png")

        # Step 3: Click the "New chat" button on the messages page
        step = "new_chat_btn"
        print(f"    [DM] Looking for 'New chat' button...")
        new_chat_btn = None
        for selector in [
            'button:has-text("New chat")',
            '[data-testid="NewDM_Button"]',
            'a[href="/messages/compose"]',
            '[aria-label="New message"]',
            'button:has-text("New message")',
        ]:
            loc = page.locator(selector).first
            try:
                await loc.wait_for(state="visible", timeout=3000)
                new_chat_btn = loc
                print(f"    [DM] Found button via: {selector}")
                break
            except:
                continue

        if not new_chat_btn:
            await page.screenshot(path=f"/tmp/dm_fail_{handle}_no_newchat.png")
            print(f"    [DM] ❌ No 'New chat' button found on messages page")
            return False

        await new_chat_btn.click()
        print(f"    [DM] Clicked 'New chat'.")
        await page.wait_for_timeout(3000)

        await page.screenshot(path=f"/tmp/dm_debug_{handle}_compose.png")

        # Step 4: Search for the target username in the "Search people" / "Search" input
        step = "search_input"
        print(f"    [DM] Looking for search input...")
        search_input = None
        for selector in [
            'input[placeholder="Search name or username"]',
            '[data-testid="searchPeople"]',
            'input[placeholder="Search people"]',
            'div[role="dialog"] input[type="text"]',
            '[data-testid="SearchBox_Search_Input"]',
        ]:
            loc = page.locator(selector).first
            try:
                await loc.wait_for(state="visible", timeout=3000)
                search_input = loc
                print(f"    [DM] Found search input via: {selector}")
                break
            except:
                continue

        if not search_input:
            await page.screenshot(path=f"/tmp/dm_fail_{handle}_no_search.png")
            print(f"    [DM] ❌ No search input found")
            return False

        # Use JavaScript click to bypass any overlay
        await search_input.evaluate("el => el.focus()")
        await page.wait_for_timeout(500)
        await search_input.type(handle, delay=80)
        print(f"    [DM] Typed handle: {handle}")
        await page.wait_for_timeout(3000)

        # Step 5: Select the user from typeahead results
        step = "typeahead"
        print(f"    [DM] Waiting for user results...")
        user_result = None
        for selector in [
            '[data-testid="TypeaheadUser"]',
            '[data-testid="typeaheadResult"]',
            'div[role="option"]',
        ]:
            loc = page.locator(selector).first
            try:
                await loc.wait_for(state="visible", timeout=8000)
                user_result = loc
                print(f"    [DM] Found user result via: {selector}")
                break
            except:
                continue

        if not user_result:
            await page.screenshot(path=f"/tmp/dm_fail_{handle}_no_typeahead.png")
            print(f"    [DM] ❌ No user results found for @{handle}")
            return False

        await user_result.click()
        print(f"    [DM] Selected user.")
        await page.wait_for_timeout(1500)

        # Step 6: Click Next to open the conversation
        step = "next_button"
        print(f"    [DM] Looking for Next button...")
        next_btn = None
        for selector in [
            '[data-testid="nextButton"]',
            'button:has-text("Next")',
        ]:
            loc = page.locator(selector).first
            try:
                await loc.wait_for(state="visible", timeout=5000)
                next_btn = loc
                break
            except:
                continue

        if next_btn:
            await next_btn.click()
            print(f"    [DM] Clicked Next.")
            await page.wait_for_timeout(2000)
        else:
            print(f"    [DM] No Next button found (may already be in conversation)")

        await page.screenshot(path=f"/tmp/dm_debug_{handle}_conversation.png")

        # Step 7: Type the message
        step = "composer"
        print(f"    [DM] Looking for message input...")
        composer = None
        for selector in [
            '[data-testid="dmComposerTextInput"]',
            'div[role="textbox"][data-testid="dmComposerTextInput"]',
            'div[data-testid="dmComposerTextInput"]',
        ]:
            loc = page.locator(selector).first
            try:
                await loc.wait_for(state="visible", timeout=8000)
                composer = loc
                print(f"    [DM] Found message input via: {selector}")
                break
            except:
                continue

        if not composer:
            await page.screenshot(path=f"/tmp/dm_fail_{handle}_no_composer.png")
            print(f"    [DM] ❌ No message input found")
            return False

        await composer.click()
        await composer.fill(message)
        print(f"    [DM] Message filled ({len(message)} chars).")
        await page.wait_for_timeout(500)

        # Step 8: Press Enter to send
        step = "send"
        print(f"    [DM] Pressing Enter to send...")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)

        # Verify: check if the message appears in the conversation
        await page.screenshot(path=f"/tmp/dm_debug_{handle}_sent.png")
        print(f"    [DM] ✅ Message sent to @{handle}.")
        return True
    except Exception as e:
        print(f"    [DM] ❌ Failed at step '{step}' for @{handle}: {e}")
        try:
            screenshot_path = f"/tmp/dm_fail_{handle}_{step}.png"
            await page.screenshot(path=screenshot_path)
            print(f"    [DM] Screenshot saved: {screenshot_path}")
        except Exception as se:
            print(f"    [DM] Could not save screenshot: {se}")
        return False

async def main():
    utc_now = datetime.now(ZoneInfo("UTC"))
    print(f"--- Running DM Scheduler (UTC: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}) ---")

    # Support filtering to specific users (set by scheduler.py)
    limit_user_ids = os.environ.get("LIMIT_TO_USER_IDS")
    if limit_user_ids:
        print(f"  Filtering to user(s): {limit_user_ids}")

    db = get_db()
    try:
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Fetch all users who have timezone + DM schedules configured
        cur.execute("""
            SELECT DISTINCT k.user_id, COALESCE(uc.timezone, 'UTC') as timezone
            FROM kols k
            JOIN user_configs uc ON k.user_id = uc.user_id
            WHERE k.status = 'active'
              AND k.dm_text IS NOT NULL AND k.dm_text != ''
              AND k.dm_day IS NOT NULL AND k.dm_day != ''
              AND k.dm_time IS NOT NULL AND k.dm_time != ''
        """)
        active_users = cur.fetchall()

        # Filter to specific users if set
        if limit_user_ids:
            allowed = set(limit_user_ids.split(','))
            active_users = [u for u in active_users if str(u['user_id']) in allowed]

        pending_dms = []
        for user_row in active_users:
            user_id = str(user_row['user_id'])
            tz_name = user_row['timezone'] if user_row['timezone'] else 'UTC'
            now = get_user_now(tz_name)
            current_day = now.strftime("%A")
            current_time_str = now.strftime("%H:%M:%S")
            print(f"  User {user_id}: tz={tz_name} day={current_day} time={current_time_str}")

            cur.execute("""
                SELECT k.*, k.user_id as u_id
                FROM kols k
                WHERE k.user_id = %s
                  AND k.status = 'active'
                  AND k.dm_text IS NOT NULL AND k.dm_text != ''
                  AND k.dm_day IS NOT NULL AND k.dm_day != ''
                  AND k.dm_time IS NOT NULL AND k.dm_time != ''
                  AND k.dm_time <= %s
                  AND k.id NOT IN (
                      SELECT kol_id FROM dm_logs
                      WHERE DATE(sent_at AT TIME ZONE %s) = DATE(%s AT TIME ZONE %s)
                        AND status = 'sent' AND direction = 'outbound'
                  )
            """, (user_id, current_time_str, tz_name, utc_now.isoformat(), tz_name))

            user_kols = cur.fetchall()
            due = [
                dm for dm in user_kols
                if current_day in [d.strip() for d in (dm.get('dm_day') or '').split(',')]
            ]
            print(f"    {len(user_kols)} passing time filter, {len(due)} matching day '{current_day}'.")
            pending_dms.extend(due)

        if not pending_dms:
            print("✅ No pending scheduled DMs for this time window.")
            return

        print(f"📨 Found {len(pending_dms)} DM(s) to send.")

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
                
                # Fetch X cookies and DM passcode from user_configs table
                cur.execute("""
                    SELECT twitter_auth_token, twitter_ct0, dm_passcode
                    FROM user_configs WHERE user_id = %s
                """, (user_id,))
                config_row = cur.fetchone()

                if not config_row or not config_row.get('twitter_auth_token'):
                    print(f"⚠️ User {user_id}: No X cookies configured. Skipping.")
                    continue

                user_auth = config_row['twitter_auth_token']
                user_ct0 = config_row['twitter_ct0']
                user_dm_passcode = config_row.get('dm_passcode')

                context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36')
                await context.add_cookies([
                    {'name': 'auth_token', 'value': user_auth, 'domain': '.x.com', 'path': '/'},
                    {'name': 'ct0', 'value': user_ct0, 'domain': '.x.com', 'path': '/'}
                ])
                
                page = await context.new_page()
                try:
                    print(f"  Navigating to x.com to verify login...")
                    await page.goto("https://x.com", wait_until="domcontentloaded", timeout=30000)
                    if not await wait_for_page_ready(page, "Login check", timeout=30000):
                        print(f"❌ User {user_id}: X.com did not load (rate limited?)")
                        await page.screenshot(path=f"/tmp/dm_fail_{user_id}_login.png")
                        await context.close()
                        continue
                    print(f"  Post-login URL: {page.url}")
                    if "login" in page.url or "i/flow/login" in page.url:
                        print(f"❌ User {user_id}: Twitter/X login failed! URL: {page.url}")
                        await context.close()
                        continue
                    print(f"  ✅ Login OK for user {user_id}")

                    # Send DMs for this user
                    for idx, kol in enumerate(user_dms):
                        handle = kol['twitter_url'].split('/')[-1] if kol['twitter_url'] else kol['name']
                        print(f"  ✉️ [{idx+1}/{len(user_dms)}] Sending DM to @{handle} (KOL: {kol['name']})...")
                        
                        success = await send_dm(page, handle, kol['dm_text'], passcode=user_dm_passcode)
                        
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
