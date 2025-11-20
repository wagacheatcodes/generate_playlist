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
    # CRITICAL FIX: Prioritize 'folder_url' because that is what the external JSON uses
    # If we have a direct file 'url', we calculate the folder from it.
    folder_url = item.get('folder_url')
    direct_url = item.get('url') or item.get('direct_source')

    # If we only have a file link, make a folder link out of it
    if not folder_url and direct_url:
        folder_url = direct_url.rsplit('/', 1)[0] + '/'
    
    # If we have neither, skip
    if not folder_url: return None

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
        "folder_url": folder_url,  # <--- UNIFIED KEY
        # We store the direct URL if we have it, but folder_url is the master key
        "url": direct_url or "" 
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
                # Normalize incoming data to ensure it has folder_url
                data = [normalize_item(x, cat_default) for x in raw_data if normalize_item(x, cat_default)]
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                print(f"✅ Seeded {len(data)} items.")
        except Exception as e:
            print(f"⚠️ Seed error: {e}")

    # Build Memory Bank based on FOLDERS
    known_folders = set()
    
    for item in data:
        f_url = item.get('folder_url')
        if f_url:
            # Normalize: ensure trailing slash and decoded characters match
            try:
                decoded_url = urllib.parse.unquote(f_url)
                known_folders.add(decoded_url)
            except:
                known_folders.add(f_url)
                
    return data, known_folders

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
    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
        name = name.replace(ext, "")
    return urllib.parse.unquote(name).strip()

def stealth_scrape(target_config):
    base_url = target_config["url"]
    category = target_config["type"]
    output_file = target_config["output"]
    seed_url = target_config.get("source")
    
    print(f"🚀 STARTING SCAN: {category.upper()}")
    
    master_list, known_folders = load_or_fetch_data(output_file, seed_url, category)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    folders_to_scan = [base_url]
    scanned_history = set()
    items_since_save = 0

    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        if current_url in scanned_history: continue
        if not current_url.startswith(base_url): continue

        # Decode URL for comparison (handling %20 vs space)
        decoded_current = urllib.parse.unquote(current_url)

        # SKIP CHECK: Do we already have this folder?
        if category == "movies":
            # Check both raw and decoded versions to be safe
            if current_url in known_folders or decoded_current in known_folders:
                # print(f"⏩ Skipping known: {decoded_current}")
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

            # --- ADD NEW ITEMS ---
            if category == "movies" and folder_files:
                # Filter samples
                valid_files = [f for f in folder_files if "sample" not in f['name'].lower()]
                if not valid_files: valid_files = folder_files
                best_file = valid_files[0]
                
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
                    "folder_url": current_url, # SAVE THE FOLDER!
                    "url": best_file['url']
                }
                master_list.append(new_item)
                # Add to known folders instantly so we don't re-add if loop circles back
                known_folders.add(urllib.parse.unquote(current_url)) 
                items_since_save += 1

            elif category == "series":
                for f in folder_files:
                     # For series, we check if file URL exists in the list manually 
                     # (Logic simplified here: just append, assuming Series scraper logic handles deep folders)
                     final_name = clean_filename(f['name'])
                     
                     # Check duplicates
                     is_duplicate = any(x.get('url') == f['url'] for x in master_list)
                     if is_duplicate: continue

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
                        "folder_url": current_url,
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
