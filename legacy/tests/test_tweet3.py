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
        await page.goto('https://x.com/thetripathi58', wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        tweets = await page.query_selector_all('article[data-testid="tweet"]')
        for i, tweet in enumerate(tweets[:2]):
            print(f"--- Tweet {i} ---")
            
            # Find the whole group of action buttons (reply, retweet, like, bookmark, views)
            group = await tweet.query_selector('[role="group"]')
            if group:
                aria = await group.get_attribute('aria-label')
                print(f"Group Aria: {repr(aria)}")
                text = await group.inner_text()
                print(f"Group InnerText: {repr(text)}")

        await browser.close()

asyncio.run(run())
