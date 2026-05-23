import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        )
        page = await ctx.new_page()

        # Step 1: Visit all-bids to get anonymous ci_session cookie
        print("Getting anonymous session cookie...")
        await page.goto('https://bidplus.gem.gov.in/all-bids', wait_until='networkidle', timeout=120000)
        await asyncio.sleep(3)

        cookies = await ctx.cookies()
        session_cookies = [c for c in cookies if 'session' in c['name'].lower() or 'gem' in c['name'].lower()]
        print(f"Cookies received: {[c['name'] for c in session_cookies]}")

        # Step 2: Try 5 different result pages with this cookie
        test_ids = ['9326749', '9326692', '9326657', '9324859', '9323923']
        for nid in test_ids:
            url = f'https://bidplus.gem.gov.in/bidding/bid/getBidResultView/{nid}'
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
            final_url = page.url
            text = await page.evaluate("() => document.body.innerText.substring(0, 300)")
            has_data = any(k in text.lower() for k in ['l1', 'winner', 'vendor', 'rank', 'awarded'])
            print(f"\nID {nid}:")
            print(f"  URL: {final_url}")
            print(f"  Has result data: {has_data}")
            print(f"  Preview: {text[:150]}")

        await b.close()

asyncio.run(test())
