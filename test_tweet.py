import asyncio
from playwright.async_api import async_playwright
import json

CREDENTIALS_PATH = "/data/.openclaw/workspace/.credentials/twitter.json"
def load_cookies():
    with open(CREDENTIALS_PATH) as f:
        return json.load(f)

async def run():
    creds = load_cookies()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies([
            {'name': 'auth_token', 'value': creds['auth_token'], 'domain': '.x.com', 'path': '/'},
            {'name': 'ct0', 'value': creds['ct0'], 'domain': '.x.com', 'path': '/'}
        ])
        page = await context.new_page()
        await page.goto('https://x.com/LearnWithBishal', wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        tweets = await page.query_selector_all('article[data-testid="tweet"]')
        for i, tweet in enumerate(tweets[:2]):
            print(f"--- Tweet {i} ---")
            
            bookmarks_el = await tweet.query_selector('button[data-testid="bookmark"]')
            if bookmarks_el:
                aria = await bookmarks_el.get_attribute('aria-label')
                print(f"Bookmark Aria: {aria}")
                # Maybe text content?
                text = await bookmarks_el.inner_text()
                print(f"Bookmark InnerText: {text}")

            views_el = await tweet.query_selector('a[href*="/analytics"]')
            if views_el:
                print("Analytics Link:", await views_el.get_attribute('aria-label'))

        await browser.close()

asyncio.run(run())
