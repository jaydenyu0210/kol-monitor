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
        await page.goto('https://x.com/LearnWithBishal', wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        tweet_ids = set()
        for i in range(5):
            tweets = await page.query_selector_all('article[data-testid="tweet"]')
            for t in tweets:
                # Get tweet link to identify uniqueness
                a = await t.query_selector('a[href*="/status/"]')
                if a:
                    href = await a.get_attribute('href')
                    tweet_ids.add(href)
            print(f"Scroll {i}: {len(tweet_ids)} unique tweets found")
            await page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(2)
            
        print(f"Total unique tweets found: {len(tweet_ids)}")

        await browser.close()

asyncio.run(run())
