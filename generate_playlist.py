import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
import time
import random
import sys

# --- CONFIGURATION ---
# We strict scan ONLY these folders.
TARGETS = [
    {"type": "movies", "url": "https://a.111477.xyz/movies/", "output": "movies.json"},
    {"type": "series", "url": "https://a.111477.xyz/tvs/",    "output": "series.json"}
]

# Headers to look like a real Chrome browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Connection": "keep-alive"
}

# -------------------------------------------

def stealth_scrape(target_config):
    base_url = target_config["url"]
    category = target_config["type"]
    
    print(f"🚀 STARTING TURBO SCAN: {category.upper()}")
    
    # Use a Session for speed (reuses TCP connections)
    session = requests.Session()
    session.headers.update(HEADERS)
    
    found_items = []
    folders_to_scan = [base_url]
    scanned_history = set()

    # Processing Loop
    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        # SAFETY: Skip if we've seen it or if it escaped the parent folder
        if current_url in scanned_history: continue
        if not current_url.startswith(base_url): 
            # This is the "Jail" - prevents going to /asiandrama/
            continue

        scanned_history.add(current_url)
        print(f"Scanning: {current_url.replace(base_url, '')} ...", end='\r')

        try:
            # Random micro-sleep to look human (0.2 to 0.5 seconds)
            time.sleep(1.5)
            
            # Fast Timeout: If server lags > 5s, skip it.
            response = session.get(current_url, timeout=5)
            
            if response.status_code == 404: continue
            if response.status_code == 429:
                print(f"\n⚠️  429 Too Many Requests. Pausing 10s...")
                time.sleep(10)
                # Put it back in queue to try later
                folders_to_scan.append(current_url) 
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a')

            for link in links:
                href = link.get('href')
                name = link.text.strip()
                
                if not href or name in ["Parent Directory", "../", "Name", "Size", "Date", "Description"]:
                    continue
                
                full_url = urllib.parse.urljoin(current_url, href)

                # 1. IS IT A FOLDER?
                if href.endswith("/"):
                    # STRICT CHECK: Only add if it is still inside our base URL
                    if full_url.startswith(base_url) and full_url not in scanned_history:
                        folders_to_scan.append(full_url)

                # 2. IS IT A VIDEO? (Grab mp4/mkv/avi)
                elif href.lower().endswith(('.mp4', '.mkv', '.avi', '.m4v')):
                    # Clean filename
                    clean_name = urllib.parse.unquote(name)
                    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
                        clean_name = clean_name.replace(ext, "")
                    
                    # Add to list (We assume 0 size to save time)
                    found_items.append({
                        "name": clean_name,
                        "url": full_url,
                        "stream_icon": "", 
                        "category_id": "1" if category == "movies" else "2",
                        "size": 0 # Scraper is blind to size for speed
                    })

        except Exception as e:
            # If it fails, just print a dot and keep moving. Don't stop.
            print(".", end="")
            pass

    print(f"\n✅ Finished {category}. Found {len(found_items)} files.")
    return found_items

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    for target in TARGETS:
        data = stealth_scrape(target)
        
        # Save JSON
        with open(target["output"], 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            print(f"💾 Saved to {target['output']}\n")

    print("🎉 ALL SCANS COMPLETE.")
