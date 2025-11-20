#!/usr/bin/env python3
"""Test script to debug creator page scraping"""
import cloudscraper
import re
import time

# Create scraper
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

# Headers
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://fortnite.gg/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Cache-Control": "max-age=0"
}

# Fetch page
time.sleep(1)
url = "https://fortnite.gg/creator?name=epic"
print(f"Fetching: {url}")
response = scraper.get(url, headers=headers, timeout=15, allow_redirects=True)

print(f"Status: {response.status_code}")
print(f"Content length: {len(response.text)}")
print(f"Content type: {response.headers.get('content-type', 'unknown')}")

# Save HTML to file
with open('/tmp/creator_page.html', 'w', encoding='utf-8') as f:
    f.write(response.text)
print("Saved HTML to /tmp/creator_page.html")

# Try current pattern
island_pattern = re.compile(
    r"<a class='island' href='/island\?code=([^']+)'>.*?"
    r"<img src='([^']+)'[^>]*alt='([^']+)'.*?"
    r"<div class='players'>.*?(\d+)\s*</div>.*?"
    r"<h3 class='island-title'>([^<]+)</h3>",
    re.DOTALL
)
matches = island_pattern.findall(response.text)
print(f"\nCurrent pattern found: {len(matches)} matches")

# Try simpler patterns
simple_island_links = re.findall(r'href=["\']?/island\?code=([^"\'>&\s]+)["\']?', response.text)
print(f"Simple island links found: {len(simple_island_links)}")
if simple_island_links:
    print(f"  First 5: {simple_island_links[:5]}")

# Look for island containers
island_containers = re.findall(r'<a[^>]*class=["\'][^"\']*island[^"\']*["\'][^>]*>', response.text)
print(f"Island link containers found: {len(island_containers)}")
if island_containers:
    print(f"  First one: {island_containers[0]}")

# Print sample HTML containing "island"
idx = response.text.find('island')
if idx > 0:
    print(f"\nFirst occurrence of 'island' at position {idx}:")
    print(response.text[max(0, idx-200):idx+600])
