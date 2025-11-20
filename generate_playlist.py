import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
import time
import argparse
import sys
import os

# --- CONFIGURATION ---
TARGETS = [
    {"type": "movies", "url": "https://a.111477.xyz/movies/", "output": "movies.json", 
     "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/movies.json"},
    
    {"type": "series", "url": "https://a.111477.xyz/tvs/",    "output": "series.json",
     "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/series.json"}
]

# CATEGORY FILES (We just download these once to ensure the player has metadata)
CATEGORIES = [
    {"output": "movie_categories.json", "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/movie_categories.json"},
    {"output": "series_categories.json", "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/series_categories.json"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}

def load_or_fetch_data(filename, external_url):
    """
    1. Tries to load local file.
    2. If missing, downloads from External Source (Seeding).
    3. Returns the data + set of known URLs to skip.
    """
    data = []
    
    # 1. Try Local Load
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📂 Loaded {len(data)} items from local {filename}")
        except:
            pass

    # 2. If empty, Try External Seed
    if not data and external_url:
        print(f"🌍 Local file missing. Seeding from: {external_url} ...")
        try:
            res = requests.get(external_url, timeout=60)
            if res.status_code == 200:
                data = res.json()
                # Save immediately so we don't have to download next time
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                print(f"✅ Seeded {len(data)} items from external source.")
            else:
                print("⚠️ External seed failed.")
        except Exception as e:
            print(f"⚠️ External seed error: {e}")

    # 3. Build Memory Banks
    known_urls = set()
    known_folders = set()
    
    for item in data:
        # Support both formats (url or direct_source)
        u = item.get('url') or item.get('direct_source')
        if u:
            known_urls.add(u)
            # If it's from our target site, remember the folder to skip scanning
            if "111477.xyz" in u:
                folder = u.rsplit('/', 1)[0] + '/'
                known_folders.add(folder)
                
    return data, known_urls, known_folders

def update_categories():
    """Downloads category files if they don't exist."""
    for cat in CATEGORIES:
        if not os.path.exists(cat["output"]):
            print(f"📥 Downloading {cat['output']}...")
            try:
                res = requests.get(cat["source"], timeout=30)
                if res.status_code == 200:
                    with open(cat["output"], 'w', encoding='utf-8') as f:
                        f.write(res.text)
            except:
                pass

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def stealth_scrape(target_config):
    base_url = target_config["url"]
    category = target_config["type"]
    output_file = target_config["output"]
    seed_url = target_config.get("source")
    
    print(f"🚀 STARTING SCAN: {category.upper()}")
    
    # Load Memory (Local or External Seed)
    master_list, known_urls, known_folders = load_or_fetch_data(output_file, seed_url)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    folders_to_scan = [base_url]
    scanned_history = set()
    items_since_save = 0

    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        if current_url in scanned_history: continue
        if not current_url.startswith(base_url): continue

        # SMART SKIP: If we already have files from this folder, skip it.
        # (Only for movies, Series we re-scan for new episodes)
        if category == "movies" and current_url in known_folders:
            continue

        scanned_history.add(current_url)
        
        display_url = current_url.replace(base_url, '')
        print(f"Scanning: {display_url if display_url else 'ROOT'} ...", flush=True)

        try:
            time.sleep(1.5) # Safe speed
            response = session.get(current_url, timeout=10)
            
            if response.status_code == 429:
                print(f"⚠️ 429 Wait...", flush=True)
                time.sleep(10)
                folders_to_scan.insert(0, current_url)
                continue
            
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a')

            for link in links:
                href = link.get('href')
                name = link.text.strip()
                if not href or name in ["Parent Directory", "../", "Name", "Size", "Date", "Description"]: continue
                
                full_url = urllib.parse.urljoin(current_url, href)

                if href.endswith("/"):
                    if full_url.startswith(base_url) and full_url not in scanned_history:
                        folders_to_scan.append(full_url)

                elif href.lower().endswith(('.mp4', '.mkv', '.avi', '.m4v')):
                    if full_url in known_urls: continue 

                    clean_name = urllib.parse.unquote(name)
                    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
                        clean_name = clean_name.replace(ext, "")
                    
                    print(f"✨ NEW: {clean_name}", flush=True)

                    # Keep format consistent with external source if possible
                    new_item = {
                        "name": clean_name,
                        "url": full_url,
                        "stream_icon": "", 
                        "category_id": "1" if category == "movies" else "2",
                        "added": int(time.time())
                    }
                    
                    master_list.append(new_item)
                    known_urls.add(full_url)
                    items_since_save += 1

            # Save periodically
            if items_since_save >= 50:
                save_data(output_file, master_list)
                items_since_save = 0

        except Exception as e:
            pass

    save_data(output_file, master_list)
    print(f"\n✅ Finished. Total items: {len(master_list)}")
    return master_list

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['movies', 'series', 'all'], default='all')
    args = parser.parse_args()

    # Ensure categories exist
    update_categories()

    if args.mode in ['movies', 'all']:
        stealth_scrape(TARGETS[0]) 

    if args.mode in ['series', 'all']:
        stealth_scrape(TARGETS[1])
