import requests
import json

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://bidplus.gem.gov.in/all-bids",
    "X-Requested-With": "XMLHttpRequest"
}

# Test 1: Get awarded bids via API
print("=== TEST 1: Awarded bids API ===")
r = requests.get(
    "https://bidplus.gem.gov.in/all-bids-data",
    params={"status": "bid_awarded", "start": 0, "rows": 5},
    headers=headers, timeout=30
)
print("Status:", r.status_code)
data = r.json()
print("Sample:", json.dumps(data, indent=2)[:3000])

# Test 2: Try different filter params
print("\n=== TEST 2: Different params ===")
r2 = requests.get(
    "https://bidplus.gem.gov.in/all-bids-data",
    params={"bid_status": "4", "start": 0, "rows": 5},
    headers=headers, timeout=30
)
print("Status:", r2.status_code)
print("Sample:", r2.text[:1000])

# Test 3: getBidResultView as JSON
print("\n=== TEST 3: Result view API ===")
r3 = requests.get(
    "https://bidplus.gem.gov.in/bidding/bid/getBidResultView/9326749",
    headers=headers, timeout=30
)
print("Status:", r3.status_code)
print("Final URL would redirect — checking content type:", r3.headers.get("content-type",""))
print("Sample:", r3.text[:500])
