import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
import time
import re

# --- CONFIGURATION ---
# Exact paths you found
MOVIES_URL = "https://a.111477.xyz/movies/"
SERIES_URL = "https://a.111477.xyz/tvs/"

OUTPUT_MOVIES = "movies.json"
OUTPUT_SERIES = "series.json"
MAX_SIZE_GB = 5.5

# Mimic a real browser to avoid blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

def get_size_gb(text_content):
    """Finds a size pattern (e.g., 2.4 GB) in any text string."""
    if not text_content: return 0
    try:
        # Look for patterns like "2.4 GB", "500M", "1.2G"
        text = text_content.upper().replace(",", "")
        match = re.search(r"(\d+(\.\d+)?)\s*(G|M|K)B?", text)
        if match:
            val = float(match.group(1))
            unit = match.group(3)
            if unit == 'G': return val
            if unit == 'M': return val / 1024
            if unit == 'K': return val / 1024 / 1024
    except:
        pass
    return 0

def scrape_folder(url, category_type, depth=0, max_depth=3):
    items = []
    
    # Safety stop for recursion
    if depth > max_depth: return []

    print(f"Scanning ({category_type}): {url}")
    
    try:
        # SLEEP to prevent 429 Errors (Crucial!)
        time.sleep(2) 
        
        response = requests.get(url, headers=HEADERS, timeout=20)
        
        if response.status_code == 404:
            print(f"   [404 Error] Path not found: {url}")
            return []
        if response.status_code == 429:
            print(f"   [429 Error] Too fast! Sleeping 30s...")
            time.sleep(30)
            # Retry once
            response = requests.get(url, headers=HEADERS, timeout=20)

        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a')

        for link in links:
            href = link.get('href')
            name = link.text.strip()
            
            # Skip "Parent Directory" or sorting links
            if name in ["Parent Directory", "../", "Name", "Size", "Date", "Description"]:
                continue
            if href.startswith("?"): continue
            
            # Build Full URL
            full_url = urllib.parse.urljoin(url, href)
            
            # 1. CHECK FOR FOLDERS (Recursion for Series)
            if href.endswith("/"):
                # Only recurse if it's the "tvs" category
                if category_type == "series":
                    print(f"   -> Entering Folder: {name}")
                    sub_items = scrape_folder(full_url, category_type, depth + 1, max_depth)
                    items.extend(sub_items)
            
            # 2. CHECK FOR VIDEO FILES
            elif href.lower().endswith(('.mp4', '.mkv', '.avi', '.m4v')):
                # Try to find size in the row
                # (In 'Index of' pages, size is usually in the text node after the link or in the next <td>)
                row_text = str(link.parent) + str(link.find_next('td')) # Combine nearby HTML to search for text
                size_gb = get_size_gb(row_text)

                # Check Size Limit
                if 0.05 < size_gb <= MAX_SIZE_GB:
                    # Clean up the name
                    clean_name = urllib.parse.unquote(name).replace(".mp4","").replace(".mkv","")
                    
                    items.append({
                        "name": clean_name,
                        "url": full_url,
                        "image": "", 
                        "category_id": "1" if category_type == "movies" else "2"
                    })
                elif size_gb > MAX_SIZE_GB:
                    pass # print(f"   [Skipped] {name} (Too large: {size_gb:.2f} GB)")

    except Exception as e:
