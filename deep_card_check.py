import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        page = await b.new_page()
        await page.goto('https://bidplus.gem.gov.in/all-bids', wait_until='networkidle', timeout=120000)
        await asyncio.sleep(4)

        # Apply awarded filter
        await page.evaluate("() => { var inputs = Array.from(document.querySelectorAll('input')); for (var inp of inputs) { var label = inp.labels && inp.labels[0] ? inp.labels[0].innerText.trim() : ''; if (label === 'Bid/RA Status') { inp.click(); } } }")
        await asyncio.sleep(3)
        await page.evaluate("() => { var cb = document.getElementById('bid_awarded'); if (cb) { cb.removeAttribute('disabled'); cb.click(); if (typeof bidStatusFilter === 'function') bidStatusFilter('bid_awarded'); } }")
        await asyncio.sleep(5)

        # Print FULL raw text + ALL links of first 3 cards
        data = await page.evaluate("""
            () => {
                var cards = Array.from(document.querySelectorAll('div.card')).slice(0,3);
                return cards.map(function(card) {
                    var links = Array.from(card.querySelectorAll('a')).map(function(a) {
                        return {text: a.innerText.trim(), href: a.href};
                    });
                    return {
                        full_text: card.innerText,
                        full_html: card.innerHTML.substring(0, 2000),
                        links: links
                    };
                });
            }
        """)
        import json
        for i, d in enumerate(data):
            print(f"\n=== CARD {i+1} FULL TEXT ===")
            print(d['full_text'])
            print(f"\n=== CARD {i+1} LINKS ===")
            print(json.dumps(d['links'], indent=2))
            print(f"\n=== CARD {i+1} HTML ===")
            print(d['full_html'])

        await b.close()

asyncio.run(check())
