import asyncio
from playwright.async_api import async_playwright

async def scrape_gem_bids():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("Setting up interceptor and navigating...")
        
        # Wait for the specific XHR response that contains the bid data
        async with page.expect_response(lambda response: "all-bids-data" in response.url) as response_info:
            await page.goto("https://bidplus.gem.gov.in/all-bids", wait_until="networkidle")

        response = await response_info.value
        print(f"Captured target request: {response.url} | Status: {response.status}")
        
        if response.status == 200:
            try:
                # Try parsing as JSON first
                data = await response.json()
                print("Successfully captured JSON data.")
            except Exception:
                # Fallback to text (if the endpoint returns HTML snippets to be injected)
                data = await response.text()
                print("Successfully captured HTML/Text data.")
                
            # Now you can pass 'data' to BeautifulSoup or process the JSON
            # print(data) 
        else:
            print("Failed to capture a 200 OK response.")

        # From here, you have the valid session cookies in 'context' for aiohttp 
        # to fetch individual bid results (/getBidResultView/{id})
        cookies = await context.cookies()
        
        await browser.close()
        return data

if __name__ == "__main__":
    asyncio.run(scrape_gem_bids())