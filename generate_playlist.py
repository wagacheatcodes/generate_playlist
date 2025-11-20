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
     "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/series.json"},

    {"type": "episodes", "url": "https://a.111477.xyz/tvs/", "output": "episodes.json",
     "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/episodes.json"}
]

CATEGORIES = [
    {"output": "movie_categories.json", "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/movie_categories.json"},
    {"output": "series_categories.json", "source": "https://raw.githubusercontent.com/dtankdempsey2/xc-vod-playlist/refs/heads/main/dist/series_categories.json"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}

# --- HELPER: FUZZY MATCHER ---
def normalize_string(s):
    """
    Turns 'Alita - Battle Angel (2019)' into 'alitabattleangel2019'.
    This allows us to catch duplicates even if punctuation differs.
    """
    if not s: return ""
    # Keep only letters and numbers, lowercase everything
    return "".join(c.lower() for c in s if c.isalnum())

def normalize_item(item, cat_type):
    folder_url = item.get('folder_url')
    direct_url = item.get('url') or item.get('direct_source')

    if not folder_url and direct_url:
        folder_url = direct_url.rsplit('/', 1)[0] + '/'
    
    if cat_type == "episodes": return item 
    if not folder_url: return None

    return {
        "series_id": item.get('series_id') if cat_type == "series" else None,
        "stream_id": item.get('stream_id') if cat_type == "movies" else None,
        "name": item.get('name') or "Unknown",
        "stream_type": "movie" if cat_type == "movies" else "series",
        "stream_icon": item.get('stream_icon') or item.get('cover') or "",
        "rating": item.get('rating') or "0",
        "added": item.get('added') or int(time.time()),
        "category_id": item.get('category_id') or ("1" if cat_type == "movies" else "2"),
        "folder_url": folder_url,
        "url": direct_url or "",
        "plot": item.get('plot') or "",
        "cast": item.get('cast') or "",
        "genre": item.get('genre') or "",
        "backdrop_path": item.get('backdrop_path') or []
    }

def load_or_fetch_data(filename, external_url, cat_type):
    data = []
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"📂 Loaded {len(data)} local items from {filename}")
        except: pass

    if not data and external_url:
        print(f"🌍 Seeding {filename} from external source...")
        try:
            res = requests.get(external_url, timeout=60)
            if res.status_code == 200:
                raw_data = res.json()
                if cat_type != "episodes":
                    data = [normalize_item(x, cat_type) for x in raw_data if normalize_item(x, cat_type)]
                else:
                    data = raw_data 
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                print(f"✅ Seeded {len(data)} items.")
        except Exception as e:
            print(f"⚠️ Seed error: {e}")

    return data

def get_memory_banks(data):
    """Creates sets of known folders and known NAMES to prevent duplicates."""
    known_folders = set()
    known_names = set() # New "Fuzzy" Memory
    
    for item in data:
        # 1. Remember exact folder URL
        f_url = item.get('folder_url')
        if f_url:
            try: known_folders.add(urllib.parse.unquote(f_url))
            except: known_folders.add(f_url)
            
        # 2. Remember fuzzy name (e.g. "alitabattleangel2019")
        name = item.get('name')
        if name:
            known_names.add(normalize_string(name))
            
    return known_folders, known_names

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def clean_filename(name):
    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
        name = name.replace(ext, "")
    return urllib.parse.unquote(name).strip()

def generate_series_id(name):
    hash_val = 0
    for char in name:
        hash_val = (hash_val * 31 + ord(char)) & 0xFFFFFFFF
    return abs(hash_val) % 1000000

def update_categories():
    for cat in CATEGORIES:
        if not os.path.exists(cat["output"]):
            try:
                res = requests.get(cat["source"], timeout=30)
                if res.status_code == 200:
                    with open(cat["output"], 'w', encoding='utf-8') as f:
                        f.write(res.text)
            except: pass

def stealth_scrape(target_config, episodes_file=None):
    base_url = target_config["url"]
    category = target_config["type"]
    output_file = target_config["output"]
    seed_url = target_config.get("source")
    
    print(f"🚀 STARTING SCAN: {category.upper()}")
    
    master_list = load_or_fetch_data(output_file, seed_url, category)
    
    episodes_list = []
    if category == "series" and episodes_file:
        episodes_list = load_or_fetch_data(episodes_file, TARGETS[2]["source"], "episodes")
    
    # Build Memory Banks
    known_folders, known_names = get_memory_banks(master_list)
    print(f"🧠 Memory: {len(known_folders)} folders, {len(known_names)} unique names.")

    session = requests.Session()
    session.headers.update(HEADERS)
    
    folders_to_scan = [base_url]
    scanned_history = set()
    items_since_save = 0

    while len(folders_to_scan) > 0:
        current_url = folders_to_scan.pop(0)
        
        if current_url in scanned_history: continue
        if not current_url.startswith(base_url): continue

        # --- INTELLIGENT SKIP LOGIC ---
        decoded_current = urllib.parse.unquote(current_url)
        
        # 1. Check Exact URL
        if decoded_current in known_folders:
             continue

        # 2. Check Fuzzy Name (Only if it's a sub-folder, not the root)
        # Extract the folder name (e.g. "Alita - Battle Angel (2019)")
        folder_name = decoded_current.rstrip('/').split('/')[-1]
        if folder_name and folder_name != "movies" and folder_name != "tvs":
            norm_name = normalize_string(folder_name)
            # If this name exists in our fuzzy memory, SKIP IT!
            if category == "movies" and norm_name in known_names:
                # print(f"⏩ Fuzzy Skip: {folder_name} matches known item.")
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

            # --- PROCESS FOUND ITEMS ---
            
            if category == "movies" and folder_files:
                valid_files = [f for f in folder_files if "sample" not in f['name'].lower()]
                if not valid_files: valid_files = folder_files
                best_file = valid_files[0]
                
                final_name = clean_filename(best_file['name'])
                print(f"✨ NEW MOVIE: {final_name}", flush=True)

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
                    "folder_url": current_url,
                    "url": best_file['url']
                }
                master_list.append(new_item)
                
                # Update Memory Instantly
                known_folders.add(decoded_current)
                known_names.add(normalize_string(final_name))
                items_since_save += 1

            elif category == "series" and folder_files:
                series_name = urllib.parse.unquote(current_url.rstrip('/').split('/')[-1])
                if "Season" in series_name:
                     series_name = urllib.parse.unquote(current_url.rstrip('/').split('/')[-2])

                s_id = generate_series_id(series_name)
                
                # Check if series exists
                series_exists = any(str(s['series_id']) == str(s_id) for s in master_list)
                
                if not series_exists:
                    print(f"✨ NEW SERIES: {series_name}", flush=True)
                    new_series = {
                        "series_id": s_id,
                        "name": series_name,
                        "folder_url": current_url,
                        "category_id": "2",
                        "stream_icon": "",
                        "added": int(time.time())
                    }
                    master_list.append(new_series)
                
                # Add Episodes
                for f in folder_files:
                     ep_name = clean_filename(f['name'])
                     season_num = "1"
                     if "Season" in current_url:
                         try: season_num = current_url.split("Season")[1].split("/")[0].strip()
                         except: pass
                     
                     # Check if episode URL is already known (deduplication)
                     if any(e['url'] == f['url'] for e in episodes_list): continue

                     new_ep = {
                         "id": f"{s_id}_{len(episodes_list)+1}",
                         "tmdb_id": s_id,
                         "season": f"Season {season_num}",
                         "episodes": [ep_name],
                         "url": f['url']
                     }
                     episodes_list.append(new_ep)

                known_folders.add(decoded_current)
                items_since_save += 1

            if items_since_save >= 50:
                save_data(output_file, master_list)
                if category == "series" and episodes_file:
                    save_data(episodes_file, episodes_list)
                items_since_save = 0

        except Exception as e:
            pass

    save_data(output_file, master_list)
    if category == "series" and episodes_file:
        save_data(episodes_file, episodes_list)
        
    print(f"\n✅ Finished. Total {category}: {len(master_list)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['movies', 'series', 'all'], default='all')
    args = parser.parse_args()

    update_categories()

    if args.mode in ['movies', 'all']:
        stealth_scrape(TARGETS[0]) 

    if args.mode in ['series', 'all']:
        stealth_scrape(TARGETS[1], episodes_file=TARGETS[2]["output"])
