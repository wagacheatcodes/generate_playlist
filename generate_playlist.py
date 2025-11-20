import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
import time
import argparse
import sys
import os
import re

# --- CONFIGURATION ---
TARGETS = [
    {"type": "movies", "url": "https://a.111477.xyz/movies/", "output": "movies.json", 
     "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/movies.json"},
    
    {"type": "series", "url": "https://a.111477.xyz/tvs/",    "output": "series.json",
     "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/series.json"}
]

CATEGORIES = [
    {"output": "movie_categories.json", "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/movie_categories.json"},
    {"output": "series_categories.json", "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/series_categories.json"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}

# --- DATA NORMALIZER ---
def normalize_item(item, category_id_default):
    url = item.get('url') or item.get('direct_source') or ""
    if not url: return None
    name = item.get('name') or "Unknown"
    return {
        "num": item.get('num'),
        "name": name,
        "stream_type": "movie" if category_id_default == "1" else "series",
        "stream_id": item.get('stream_id'),
        "stream_icon": item.get('stream_icon') or item.get('cover') or "",
        "rating": item.get('rating') or "0",
        "added": item.get('added') or int(time.time()),
        "category_id": item.get('category_id') or category_id_default,
        "container_extension": "mp4",
        "url": url
    }

def load_or_fetch_data(filename, external_url, category_type):
    data = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📂 Loaded {len(data)} local items.")
        except: pass

    if not data and external_url:
        print(f"🌍 Seeding from: {external_url} ...")
        try:
            res = requests.get(external_url, timeout=60)
            if res.status_code == 200:
                raw_data = res.json()
                cat_default = "1" if category_type == "movies" else "2"
                data = [normalize_item(x, cat_default) for x in raw_data if normalize_item(x, cat_default)]
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                print(f"✅ Seeded {len(data)} items.")
        except Exception as e:
            print(f"⚠️ Seed error: {e}")

    known_folders = set()
    # Use a dict to track known movies by NAME to prevent duplicates
    known_names = set() 
    
    for item in data:
        if not item or 'url' not in item: continue
        u = item['url']
        if "111477.xyz" in u:
            folder = u.rsplit('/', 1)[0] + '/'
            known_folders.add(folder)
        
        # Clean name for deduplication
        clean_n = item['name'].lower().strip()
        known_names.add(clean_n)
                
    return data, known_names, known_folders

def update_categories():
    for cat in CATEGORIES:
        if not os.path.exists(cat["output"]):
            try:
                res = requests.get(cat["source"], timeout=30)
                if res.status_code == 200:
                    with open(cat["output"], 'w', encoding='utf-8') as f:
                        f.write(res.text)
            except: pass

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def clean_filename(name):
    # Remove extensions
    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
        name = name.replace(ext, "")
    # Remove common junk (optional, but keeps list clean)
    # name = re.sub(r'\d{4}.*', '', name) # Remove year and everything after? (Risky)
    return urllib.parse.unquote(name).strip()

def stealth_scrape(target_config):
    base_url = target_config["url"]
    category = target_config["type"]
    output_file = target_config["output"]
    seed_url = target_config.get("source")
    
    print(f"🚀 STARTING SCAN: {category.upper()}")
    
    master_list, known_names, known_folders = load_or_fetch_data(output_file, seed_url, category)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    folders_to_scan = [base_url]
    scanned_history = set()
    items_since_save = 0

    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        if current_url in scanned_history: continue
        if not current_url.startswith(base_url): continue

        # SKIP KNOWN FOLDERS
        if category == "movies" and current_url in known_folders:
            continue

        scanned_history.add(current_url)
        
        display_url = current_url.replace(base_url, '')
        print(f"Scanning: {display_url if display_url else 'ROOT'} ...", flush=True)

        try:
            time.sleep(1.5)
            response = session.get(current_url, timeout=10)
            
            if response.status_code == 429:
                print(f"⚠️ 429 Wait...", flush=True)
                time.sleep(10)
                folders_to_scan.insert(0, current_url)
                continue
            
            if response.status_code != 200: continue

            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a')
            
            # Temp list to hold files found in THIS folder
            folder_files = []

            for link in links:
                href = link.get('href')
                name = link.text.strip()
                if not href or name in ["Parent Directory", "../", "Name", "Size", "Date", "Description"]: continue
                
                full_url = urllib.parse.urljoin(current_url, href)

                if href.endswith("/"):
                    if full_url.startswith(base_url) and full_url not in scanned_history:
                        folders_to_scan.append(full_url)

                elif href.lower().endswith(('.mp4', '.mkv', '.avi', '.m4v')):
                    folder_files.append({"name": name, "url": full_url})

            # --- HIGHLANDER LOGIC: THERE CAN BE ONLY ONE ---
            if category == "movies" and folder_files:
                # If we found files, pick the BEST one.
                # Heuristic: Prefer 1080p > 720p. Prefer x264 > x265 (compatibility).
                # Simple fallback: Pick the first one (usually main movie).
                
                # Filter out samples
                valid_files = [f for f in folder_files if "sample" not in f['name'].lower()]
                if not valid_files: valid_files = folder_files # Fallback
                
                # Pick ONE
                best_file = valid_files[0]
                
                # Check if we already have this movie by NAME in our database
                # This prevents adding "Avatar (2009)" if "Avatar.2009.1080p.mp4" exists
                # Note: This relies on the folder name usually being the movie name.
                
                # For now, just add the SINGLE best file from this folder.
                # Since each folder represents ONE movie usually.
                
                final_name = clean_filename(best_file['name'])
                
                print(f"✨ NEW: {final_name}", flush=True)

                new_item = {
                    "num": len(master_list) + 1,
                    "name": final_name,
                    "stream_type": "movie",
                    "stream_id": int(time.time()) + len(master_list),
                    "stream_icon": "", 
                    "rating": "0",
                    "added": int(time.time()),
                    "category_id": "1",
                    "container_extension": "mp4",
                    "url": best_file['url']
                }
                master_list.append(new_item)
                items_since_save += 1

            # For Series, we usually WANT all episodes, so we don't filter unique there.
            elif category == "series":
                for f in folder_files:
                     final_name = clean_filename(f['name'])
                     new_item = {
                        "num": len(master_list) + 1,
                        "name": final_name,
                        "stream_type": "series",
                        "stream_id": int(time.time()) + len(master_list),
                        "stream_icon": "", 
                        "rating": "0",
                        "added": int(time.time()),
                        "category_id": "2",
                        "container_extension": "mp4",
                        "url": f['url']
                    }
                     master_list.append(new_item)
                     items_since_save += 1

            if items_since_save >= 50:
                save_data(output_file, master_list)
                items_since_save = 0

        except Exception as e:
            pass

    save_data(output_file, master_list)
    print(f"\n✅ Finished. Total items: {len(master_list)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['movies', 'series', 'all'], default='all')
    args = parser.parse_args()

    update_categories()

    if args.mode in ['movies', 'all']:
        stealth_scrape(TARGETS[0]) 

    if args.mode in ['series', 'all']:
        stealth_scrape(TARGETS[1])
