import asyncio
from playwright.async_api import async_playwright

async def investigate():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        page = await b.new_page()

        # Intercept all network requests to find API endpoints
        api_calls = []
        async def handle_request(request):
            url = request.url
            if any(k in url for k in ['api', 'json', 'result', 'award', 'winner', 'bid']):
                api_calls.append({'method': request.method, 'url': url})

        page.on('request', handle_request)

        print("Loading GEM all-bids with awarded filter...")
        await page.goto('https://bidplus.gem.gov.in/all-bids', wait_until='networkidle', timeout=120000)
        await asyncio.sleep(3)

        # Apply awarded filter
        await page.evaluate("() => { var inputs = Array.from(document.querySelectorAll('input')); for (var inp of inputs) { var label = inp.labels && inp.labels[0] ? inp.labels[0].innerText.trim() : ''; if (label === 'Bid/RA Status') { inp.click(); return; } } }")
        await asyncio.sleep(3)
        await page.evaluate("() => { var cb = document.getElementById('bid_awarded'); if (cb) { cb.removeAttribute('disabled'); cb.click(); if (typeof bidStatusFilter === 'function') bidStatusFilter('bid_awarded'); } }")
        await asyncio.sleep(5)

        # Now click on first card's result link directly
        result_link = await page.evaluate("""
            () => {
                var cards = document.querySelectorAll('div.card');
                for (var card of cards) {
                    var links = Array.from(card.querySelectorAll('a'));
                    for (var a of links) {
                        if (a.href.indexOf('getBidResultView') > -1) return a.href;
                    }
                }
                return '';
            }
        """)
        print("Result link found:", result_link)

        if result_link:
            print("Navigating to result page...")
            await page.goto(result_link, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(5)
            print("Final URL:", page.url)
            print("Page title:", await page.title())
            text = await page.evaluate("() => document.body.innerText")
            print("PAGE TEXT (first 1000 chars):", text[:1000])

        import json
        print("\n=== API CALLS INTERCEPTED ===")
        for call in api_calls[:20]:
            print(call)

        await b.close()

asyncio.run(investigate())
