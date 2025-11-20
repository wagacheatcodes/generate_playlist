import requests
from bs4 import BeautifulSoup
import json
import re
import urllib.parse

# --- CONFIGURATION ---
BASE_URL = "https://a.111477.xyz/"
MOVIES_PATH = "Movies/" 
SERIES_PATH = "Series/"
MAX_SIZE_GB = 5.5
OUTPUT_MOVIES = "movies.json"
OUTPUT_SERIES = "series.json"

# Allowed video extensions
VIDEO_EXT = ('.mp4', '.mkv', '.avi', '.m4v')

def get_size_in_gb(size_str):
    """Converts size strings (e.g., '500 MB', '2.1 GB') to float GB"""
    if not size_str: return 0
    size_str = size_str.upper().replace(',', '')
    try:
        match = re.search(r"([\d\.]+)", size_str)
        if not match: return 0
        val = float(match.group(1))
        
        if 'GB' in size_str: return val
        elif 'MB' in size_str: return val / 1024
        elif 'KB' in size_str: return val / 1024 / 1024
    except:
        return 0
    return 0

def scrape_recursive(url, category_name, depth=0, max_depth=3):
    """
    Scrapes a directory. 
    If it finds a video file -> adds to list.
    If it finds a folder -> dives in (recursion) to find series episodes.
    """
    items = []
    print(f"[{category_name}] Scanning: {url}")
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a')
        
        for link in links:
            href = link.get('href')
            name = link.text.strip()
            
            # Skip navigation links
            if href in ['../', './', '/'] or name == 'Parent Directory':
                continue
            
            # Construct full URL
            # Handle cases where href is relative or absolute
            if href.startswith('http'):
                full_url = href
            else:
                full_url = urllib.parse.urljoin(url, href)

            # 1. IS IT A VIDEO FILE?
            if href.endswith(VIDEO_EXT):
                # Try to find size
                row_text = link.parent.text if link.parent else ""
                # Look for size pattern like "1.2 GB"
                size_match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB|KB)", str(link.parent) + str(link.find_next('td')))
                
                file_size = 0
                if size_match:
                    file_size = get_size_in_gb(f"{size_match.group(1)} {size_match.group(2)}")
                
                # Check Size Limit (Only for Movies usually, but applied generally here)
                # We skip very small files (samples) < 0.05GB
                if 0.05 < file_size <= MAX_SIZE_GB:
                    # Clean up name (remove extension and URL encoding)
                    clean_name = urllib.parse.unquote(name)
                    for ext in VIDEO_EXT:
                        clean_name = clean_name.replace(ext, "")
                    
                    items.append({
                        "name": clean_name,
                        "url": full_url,
                        "image": "", 
                        "category_id": "1" 
                    })
                    # print(f"  -> Found: {clean_name} ({file_size:.2f} GB)")

            # 2. IS IT A FOLDER? (And are we scraping Series?)
            elif href.endswith('/'):
                if category_name == "Series" and depth < max_depth:
                    # Recursive Call!
                    # We pass depth+1 to prevent infinite loops
                    sub_items = scrape_recursive(full_url, category_name, depth + 1, max_depth)
                    items.extend(sub_items)

    except Exception as e:
        print(f"Error scraping {url}: {e}")
    
    return items

# --- EXECUTION ---

print("--- STARTING MOVIE SCAN ---")
# Movies are usually flat, so max_depth=0 or 1 is enough
movies = scrape_recursive(BASE_URL + MOVIES_PATH, "Movies", max_depth=1)

print(f"\n--- STARTING SERIES SCAN ---")
# Series need depth to go into Season folders
series = scrape_recursive(BASE_URL + SERIES_PATH, "Series", max_depth=3)

# --- SAVE FILES ---
print(f"\nSaving {len(movies)} movies to {OUTPUT_MOVIES}...")
with open(OUTPUT_MOVIES, 'w') as f:
    json.dump(movies, f, indent=4)

print(f"Saving {len(series)} episodes to {OUTPUT_SERIES}...")
with open(OUTPUT_SERIES, 'w') as f:
    json.dump(series, f, indent=4)

print("Done!")
