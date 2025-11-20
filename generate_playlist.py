import requests
from bs4 import BeautifulSoup
import json
import urllib.parse

# --- CONFIGURATION ---
BASE_URL = "https://a.111477.xyz" # No trailing slash
MOVIES_PATHS = ["/Movies", "/movies", "/Movie", "/movie"] # Will try all these variations
SERIES_PATHS = ["/Series", "/series", "/TV", "/tv"]
OUTPUT_MOVIES = "movies.json"
OUTPUT_SERIES = "series.json"

# Headers to look like a real browser (Bypasses basic blocking)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8",
    "Referer": BASE_URL
}

def get_alist_files(path):
    """
    Attempts to fetch files using the 'Alist' API (common for these sites).
    """
    api_url = f"{BASE_URL}/api/fs/list"
    payload = {
        "path": path,
        "password": "",
        "page": 1,
        "per_page": 0,
        "refresh": False
    }
    try:
        print(f"   [API Check] Trying Alist API for {path}...")
        r = requests.post(api_url, json=payload, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('code') == 200:
                print("   [SUCCESS] Detected Alist API!")
                return data['data']['content'] # Returns list of file objects
    except:
        pass
    return None

def scan_path(category_name, paths_to_try):
    items = []
    found_files = False

    for path in paths_to_try:
        if found_files: break
        
        full_url = BASE_URL + path
        print(f"\n--- Scanning {category_name}: {path} ---")
        
        # METHOD 1: Try Alist API (Most likely for this site)
        api_files = get_alist_files(path)
        if api_files:
            found_files = True
            for f in api_files:
                if f['is_dir']:
                    # If it's a series folder, we might need recursion (skipped for simplicity here)
                    continue 
                
                # Check extensions
                name = f['name']
                if name.lower().endswith(('.mp4', '.mkv', '.avi')):
                    # Alist usually gives direct links or proxy links
                    # We construct the raw link
                    raw_url = f"{BASE_URL}/d{path}/{name}"
                    # Or sometimes: f['sign'] might be needed. 
                    # For public Alist, /d/path/file usually works.
                    
                    items.append({
                        "name": name.replace(".mp4","").replace(".mkv",""),
                        "url": urllib.parse.quote(raw_url, safe=":/"),
                        "image": f.get('thumb', ""),
                        "category_id": "1"
                    })
            print(f"   Found {len(items)} items via API.")
            break

        # METHOD 2: Standard HTML Scraping (Fallback)
        try:
            print("   [HTML Check] Trying standard scraping...")
            r = requests.get(full_url, headers=HEADERS, timeout=15)
            
            # DEBUG: Print what we actually see
            if r.status_code != 200:
                print(f"   [ERROR] Status Code: {r.status_code}")
                continue
            
            soup = BeautifulSoup(r.text, 'html.parser')
            title = soup.title.string if soup.title else "No Title"
            print(f"   [DEBUG] Page Title: {title}")
            
            if "Just a moment" in title or "Cloudflare" in title:
                print("   [BLOCKED] Cloudflare is blocking the script.")
                continue

            links = soup.find_all('a')
            count = 0
            for link in links:
                href = link.get('href')
                if not href: continue
                
                if href.lower().endswith(('.mp4', '.mkv', '.avi')):
                    final_url = urllib.parse.urljoin(full_url + "/", href)
                    items.append({
                        "name": link.text.strip(),
                        "url": final_url,
                        "image": "",
                        "category_id": "1"
                    })
                    count += 1
            
            if count > 0:
                found_files = True
                print(f"   Found {count} items via HTML.")
                
        except Exception as e:
            print(f"   [ERROR] {e}")

    return items

# --- RUN ---
movies = scan_path("Movies", MOVIES_PATHS)
series = scan_path("Series", SERIES_PATHS)

# Save
print(f"\nTotal Movies Found: {len(movies)}")
print(f"Total Series Found: {len(series)}")

with open(OUTPUT_MOVIES, 'w') as f:
    json.dump(movies, f, indent=4)
with open(OUTPUT_SERIES, 'w') as f:
    json.dump(series, f, indent=4)
