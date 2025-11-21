import requests
from bs4 import BeautifulSoup
import json
import urllib.parse
import time
import argparse
import sys
import os

# --- CONFIGURATION ---
# EXTERNAL SOURCES REMOVED. WE RELY ON LOCAL DATA NOW.
TARGETS = [
    {"type": "movies", "url": "https://a.111477.xyz/movies/", "output": "movies.json"},
    {"type": "series", "url": "https://a.111477.xyz/tvs/",    "output": "series.json"},
    {"type": "episodes", "url": "https://a.111477.xyz/tvs/", "output": "episodes.json"}
]

# We assume category files exist locally now.
CATEGORIES = [
    {"output": "movie_categories.json"},
    {"output": "series_categories.json"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}

# --- STABLE ID GENERATOR ---
def generate_id(name):
    if not name: return 0
    clean = "".join(c.lower() for c in name if c.isalnum())
    hash_val = 0
    for char in clean:
        hash_val = (hash_val * 31 + ord(char)) & 0xFFFFFFFF
    return abs(hash_val) % 1000000000

def clean_filename(name):
    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
        name = name.replace(ext, "")
    return urllib.parse.unquote(name).strip()

def normalize_string(s):
    if not s: return ""
    return "".join(c.lower() for c in s if c.isalnum())

def load_data(filename):
    """Loads local JSON file only. No external fetching."""
    data = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📂 Loaded {len(data)} items from local {filename}")
        except Exception as e:
            print(f"⚠️ Error loading {filename}: {e}")
    else:
        print(f"⚠️ File {filename} not found. Starting fresh scan.")
    return data

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def get_memory_banks(data):
    known_folders = set()
    known_names = set() 
    
    for item in data:
        f_url = item.get('folder_url')
        if f_url:
            try: known_folders.add(urllib.parse.unquote(f_url))
            except: known_folders.add(f_url)
            
        name = item.get('name')
        if name:
            known_names.add(normalize_string(name))
            
    return known_folders, known_names

def stealth_scrape(target_config, episodes_file=None):
    base_url = target_config["url"]
    category = target_config["type"]
    output_file = target_config["output"]
    
    print(f"🚀 STARTING INDEPENDENT SCAN: {category.upper()}")
    
    # Load only local data
    master_list = load_data(output_file)
    
    episodes_list = []
    if category == "series" and episodes_file:
        episodes_list = load_data(episodes_file)
    
    known_folders, known_names = get_memory_banks(master_list)
    print(f"🧠 Memory: {len(known_folders)} folders, {len(known_names)} unique names known.")

    session = requests.Session()
    session.headers.update(HEADERS)
    
    folders_to_scan = [base_url]
    scanned_history = set()
    items_since_save = 0

    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        if current_url in scanned_history: continue
        if not current_url.startswith(base_url): continue

        decoded_current = urllib.parse.unquote(current_url)
        
        # CHECK MEMORY: Do we already have this folder?
        if decoded_current in known_folders:
             continue

        # CHECK FUZZY NAME: Do we have this Movie/Series by name?
        folder_name = decoded_current.rstrip('/').split('/')[-1]
        if folder_name and folder_name != "movies" and folder_name != "tvs":
            norm_name = normalize_string(folder_name)
            if norm_name in known_names: continue

        scanned_history.add(current_url)
        
        display_url = current_url.replace(base_url, '')
        print(f"Scanning: {display_url if display_url else 'ROOT'} ...", flush=True)

        try:
            time.sleep(1.5)
            response = session.get(current_url, timeout=10)
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

            # --- ADD NEW DATA ---
            if category == "movies" and folder_files:
                valid = [f for f in folder_files if "sample" not in f['name'].lower()]
                best = valid[0] if valid else folder_files[0]
                
                final_name = clean_filename(best['name'])
                print(f"✨ NEW MOVIE: {final_name}", flush=True)

                # GENERATE STABLE ID
                s_id = generate_id(final_name)

                master_list.append({
                    "num": len(master_list) + 1,
                    "name": final_name,
                    "stream_type": "movie",
                    "stream_id": s_id,
                    "stream_icon": "", 
                    "rating": "0",
                    "added": int(time.time()),
                    "category_id": "1",
                    "container_extension": "mp4",
                    "folder_url": current_url,
                    "url": best['url']
                })
                known_folders.add(decoded_current)
                known_names.add(normalize_string(final_name))
                items_since_save += 1

            elif category == "series" and folder_files:
                series_name = urllib.parse.unquote(current_url.rstrip('/').split('/')[-1])
                if "Season" in series_name:
                     series_name = urllib.parse.unquote(current_url.rstrip('/').split('/')[-2])

                s_id = generate_id(series_name)
                
                # Only add Series Metadata if it's actually new
                if not any(str(s['series_id']) == str(s_id) for s in master_list):
                    print(f"✨ NEW SERIES: {series_name}", flush=True)
                    master_list.append({
                        "series_id": s_id,
                        "name": series_name,
                        "folder_url": current_url,
                        "category_id": "2",
                        "stream_icon": "",
                        "added": int(time.time())
                    })
                
                # Add Episodes
                for f in folder_files:
                     if any(e['url'] == f['url'] for e in episodes_list): continue
                     
                     ep_name = clean_filename(f['name'])
                     season_num = "1"
                     if "Season" in current_url:
                         try: season_num = current_url.split("Season")[1].split("/")[0].strip()
                         except: pass
                     
                     episodes_list.append({
                         "id": f"{s_id}_{len(episodes_list)+1}",
                         "tmdb_id": s_id,
                         "season": f"Season {season_num}",
                         "episodes": [ep_name],
                         "url": f['url']
                     })
                
                known_folders.add(decoded_current)
                known_names.add(normalize_string(series_name))
                items_since_save += 1

            if items_since_save >= 50:
                save_data(output_file, master_list)
                if category == "series": save_data(episodes_file, episodes_list)
                items_since_save = 0

        except Exception as e: pass

    save_data(output_file, master_list)
    if category == "series": save_data(episodes_file, episodes_list)
    print(f"\n✅ Finished {category}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['movies', 'series', 'all'], default='all')
    args = parser.parse_args()

    if args.mode in ['movies', 'all']: stealth_scrape(TARGETS[0]) 
    if args.mode in ['series', 'all']: stealth_scrape(TARGETS[1], episodes_file=TARGETS[2]["output"])
