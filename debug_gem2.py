import asyncio
from playwright.async_api import async_playwright

async def main():
    api_calls = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Intercept all network requests
        page.on("request", lambda req: api_calls.append(req.url) if any(
            x in req.url for x in ["bid", "search", "filter", "ajax", "api", "json", "list"]
        ) else None)
        
        await page.goto("https://bidplus.gem.gov.in/all-bids")
        await page.wait_for_timeout(10000)
        
        print("\n=== API CALLS DETECTED ===")
        for url in api_calls:
            print(url)
        
        # Try clicking "Bid/RA" menu item visible in the nav
        try:
            await page.click("a:has-text('Bid/RA')")
            await page.wait_for_timeout(5000)
            print("\n=== AFTER CLICKING Bid/RA ===")
            for url in api_calls[-10:]:
                print(url)
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            bid_links = [l for l in links if "getBidResultView" in l or "bidResult" in l.lower()]
            print("Bid links after click:", bid_links[:5])
            html = await page.content()
            with open("gem_page2.html", "w") as f:
                f.write(html)
            print("Saved gem_page2.html —", len(html), "chars")
        except Exception as e:
            print("Click error:", e)
        
        await browser.close()

asyncio.run(main())
