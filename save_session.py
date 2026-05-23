import asyncio
import json
from playwright.async_api import async_playwright

async def save():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        ctx = await b.new_context()
        page = await ctx.new_page()
        await page.goto('https://sso.gem.gov.in/ARXSSO/oauth/login', timeout=60000)
        print("=== LOGIN IN THE BROWSER ===")
        print("Enter your email/mobile + OTP")
        print("Wait until you see GEM dashboard")
        input("Press ENTER after fully logged in...")
        cookies = await ctx.cookies()
        with open('gem_session.json', 'w') as f:
            json.dump(cookies, f)
        print(f"Saved {len(cookies)} cookies to gem_session.json")

        # Verify it works
        await page.goto('https://bidplus.gem.gov.in/bidding/bid/getBidResultView/9326749', timeout=60000)
        await asyncio.sleep(3)
        text = await page.evaluate("() => document.body.innerText.substring(0,300)")
        print("RESULT PAGE PREVIEW:", text)
        await b.close()

asyncio.run(save())
