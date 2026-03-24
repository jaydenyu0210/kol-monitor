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
        await page.goto('https://x.com/Saboo_Shubham_', wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)
        
        all_tweets = []
        for _ in range(5):
            tweets = await page.query_selector_all('article[data-testid="tweet"]')
            all_tweets.extend(tweets)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
        print(f"Total tweets found: {len(set(all_tweets))}")

        await browser.close()

asyncio.run(run())
