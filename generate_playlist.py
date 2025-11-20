import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
import time
import random
import argparse
import sys

# --- CONFIGURATION ---
# STRICT TARGETS: The script is allowed to look ONLY here.
TARGETS = [
    {"type": "movies", "url": "https://a.111477.xyz/movies/", "output": "movies.json"},
    {"type": "series", "url": "https://a.111477.xyz/tvs/",    "output": "series.json"} 
]

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}

def stealth_scrape(target_config):
    base_url = target_config["url"]
    category = target_config["type"]
    
    print(f"🚀 STARTING SCAN: {category.upper()} ({base_url})")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    found_items = []
    folders_to_scan = [base_url]
    scanned_history = set()

    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        # --- THE JAIL ---
        # 1. Check history
        if current_url in scanned_history: continue
        
        # 2. STRICT LOCK: If URL does not start with the base (e.g. /tvs/), KILL IT.
        # This prevents wandering into /asiandrama/
        if not current_url.startswith(base_url): 
            continue

        scanned_history.add(current_url)
        
        # Print progress (flush=True forces it to show in GitHub logs instantly)
        display_url = current_url.replace(base_url, '')
        if not display_url: display_url = "ROOT"
        print(f"Scanning: {display_url} ...", flush=True)

        try:
            # --- SAFE SPEED ---
            # 1.5 seconds is the "Sweet Spot". 
            # Fast enough to finish, slow enough to avoid 429 errors.
            time.sleep(1.5)
            
            response = session.get(current_url, timeout=10)
            
            if response.status_code == 429:
                print(f"⚠️  429 Too Many Requests. Sleeping 10s...", flush=True)
                time.sleep(10)
                folders_to_scan.insert(0, current_url) # Retry
                continue
            
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a')

            for link in links:
                href = link.get('href')
                name = link.text.strip()
                
                if not href or name in ["Parent Directory", "../", "Name", "Size", "Date", "Description"]:
                    continue
                
                full_url = urllib.parse.urljoin(current_url, href)

                # 1. FOLDERS
                if href.endswith("/"):
                    # Only add if it stays inside the Jail
                    if full_url.startswith(base_url) and full_url not in scanned_history:
                        folders_to_scan.append(full_url)

                # 2. VIDEO FILES (Blind Grab - Faster)
                elif href.lower().endswith(('.mp4', '.mkv', '.avi', '.m4v')):
                    clean_name = urllib.parse.unquote(name)
                    # Remove extensions for cleaner UI
                    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
                        clean_name = clean_name.replace(ext, "")
                    
                    found_items.append({
                        "name": clean_name,
                        "url": full_url,
                        "stream_icon": "", 
                        "category_id": "1" if category == "movies" else "2",
                        "size": 0 
                    })

        except Exception as e:
            pass

    print(f"\n✅ Finished {category}. Found {len(found_items)} files.")
    return found_items

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    # Parse arguments to know which robot we are
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['movies', 'series', 'all'], default='all')
    args = parser.parse_args()

    # Robot 1: Movies
    if args.mode in ['movies', 'all']:
        data = stealth_scrape(TARGETS[0]) 
        with open(TARGETS[0]["output"], 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    # Robot 2: Series (Strictly /tvs/)
    if args.mode in ['series', 'all']:
        data = stealth_scrape(TARGETS[1])
        with open(TARGETS[1]["output"], 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
