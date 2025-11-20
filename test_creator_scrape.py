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

if response.status_code != 200:
    print(f"ERROR: Got status {response.status_code}")
    print(response.text[:500])
    exit(1)

html = response.text

# Find the first complete island entry
start = html.find("<a href='/island?code=")
if start < 0:
    start = html.find('<a href="/island?code=')

if start >= 0:
    # Find the end of this island entry (next <a> tag or end of section)
    end = html.find('<a href=', start + 10)
    if end < 0:
        end = start + 2000  # Get 2000 chars

    island_html = html[start:end]

    print("\n" + "="*80)
    print("FULL HTML OF FIRST ISLAND ENTRY:")
    print("="*80)
    print(island_html)
    print("="*80)

    # Try to extract data manually
    code_match = re.search(r'code=([^"\'>&\s]+)', island_html)
    img_match = re.search(r'<img[^>]+alt=["\']([^"\']+)["\']', island_html)
    players_match = re.search(r'<div class=["\']players["\'][^>]*>(.*?)</div>', island_html, re.DOTALL)

    print("\nMANUAL EXTRACTION:")
    print(f"Code: {code_match.group(1) if code_match else 'NOT FOUND'}")
    print(f"Title (from img alt): {img_match.group(1) if img_match else 'NOT FOUND'}")
    if players_match:
        players_html = players_match.group(1)
        print(f"Players div content: {players_html[:200]}")
        # Try to find number in players div
        num_match = re.search(r'(\d+)', players_html)
        print(f"Player count: {num_match.group(1) if num_match else 'NOT FOUND'}")
    else:
        print("Players div: NOT FOUND")

# Test the new pattern
print("\n" + "="*80)
print("TESTING REGEX PATTERN:")
print("="*80)

pattern = re.compile(
    r'<a href=["\']?/island\?code=([^"\'>&\s]+)["\']?[^>]*class=["\'][^"\']*island[^"\']*["\'][^>]*>.*?'
    r'<img src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']+)["\'].*?'
    r'<div class=["\']players["\']>.*?(\d+)\s*</div>',
    re.DOTALL | re.IGNORECASE
)

matches = pattern.findall(html)
print(f"Pattern matched: {len(matches)} islands")

if matches:
    print("\nFirst 3 matches:")
    for i, match in enumerate(matches[:3]):
        code, img_url, title, players = match
        print(f"{i+1}. {title} - Code: {code} - Players: {players}")
