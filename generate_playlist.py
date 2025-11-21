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
    {"type": "movies", "url": "https://a.111477.xyz/movies/", "output": "movies.json"},
    {"type": "series", "url": "https://a.111477.xyz/tvs/",    "output": "series.json"},
    {"type": "episodes", "url": "https://a.111477.xyz/tvs/", "output": "episodes.json"}
]

CAT_FILES = {
    "movies": "movie_categories.json",
    "series": "series_categories.json"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}

# --- IMDB STEALTH API ---
def get_imdb_metadata(name, content_type):
    """
    Uses IMDb's hidden 'Suggestion API' to get Metadata safely.
    """
    if not name: return None
    
    # Clean name for search (e.g. "Avatar (2009)" -> "avatar")
    clean = "".join(c.lower() for c in name if c.isalnum())
    if len(clean) < 2: return None
    
    # IMDb Suggestion API URL
    first_char = clean[0]
    url = f"https://v2.sg.media-imdb.com/suggestion/{first_char}/{urllib.parse.quote(name)}.json"

    try:
        time.sleep(0.2) # Be polite
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if "d" in data and len(data["d"]) > 0:
                # Find the best match
                for match in data["d"]:
                    is_movie = match.get('q') == 'feature'
                    is_series = match.get('q') in ['TV series', 'TV mini-series']
                    
                    if (content_type == "movies" and is_movie) or \
                       (content_type == "series" and is_series) or \
                       (match.get('l').lower() == name.lower()): 
                        
                        # High Res Image Trick (Remove size limit from URL)
                        img = match.get('i', {}).get('imageUrl', '')
                        if img: img = img.replace(".jpg", "UX1000.jpg")

                        return {
                            "tmdb_id": match.get('id'), # Use IMDb ID (tt12345)
                            "name": match.get('l'),
                            "year": match.get('y'),
                            "stream_icon": img,
                            "backdrop_path": [img], # Use poster as backdrop fallback
                            "rating": "7.0", # Default good rating since API doesn't give it
                            "genre": match.get('s', 'General') # Usually contains "Actor, Movie" etc.
                        }
    except Exception:
        pass
    return None

# --- HELPERS ---
def clean_filename(name):
    decoded = urllib.parse.unquote(name)
    for ext in ['.mp4', '.mkv', '.avi', '.m4v']:
        decoded = decoded.replace(ext, "")
    return decoded.strip()

def generate_id(name):
    clean = "".join(c.lower() for c in name if c.isalnum())
    hash_val = 0
    for char in clean:
        hash_val = (hash_val * 31 + ord(char)) & 0xFFFFFFFF
    return abs(hash_val) % 1000000000

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return []

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- DYNAMIC CATEGORY MANAGER ---
def update_category_file(cat_type, genre_name, existing_cats):
    """Adds a new genre to categories.json if it doesn't exist."""
    # Default 'All' category
    if not any(c['category_id'] == "0" for c in existing_cats):
        existing_cats.insert(0, {"category_id": "0", "category_name": "All", "parent_id": 0})

    # Simple normalization
    if not genre_name: genre_name = "General"
    
    # Check if exists
    for c in existing_cats:
        if c['category_name'].lower() == genre_name.lower():
            return c['category_id']
    
    # Create new
    new_id = str(100 + len(existing_cats))
    existing_cats.append({
        "category_id": new_id,
        "category_name": genre_name,
        "parent_id": 0
    })
    
    # Save immediately
    save_json(CAT_FILES[cat_type], existing_cats)
    return new_id

# --- SCRAPER ---
def stealth_scrape(target_config, episodes_file=None):
    base_url = target_config["url"]
    category = target_config["type"]
    output_file = target_config["output"]
    
    print(f"🚀 STARTING FRESH SCAN: {category.upper()}")
    
    master_list = load_json(output_file)
    episodes_list = []
    if category == "series" and episodes_file:
        episodes_list = load_json(episodes_file)
    
    # Load Categories
    cat_file = CAT_FILES["movies" if category == "movies" else "series"]
    categories = load_json(cat_file)

    # Memory Bank
    known_folders = set(item['folder_url'] for item in master_list if 'folder_url' in item)

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
        
        # SKIP KNOWN FOLDERS (Movies only)
        if category == "movies" and decoded_current in known_folders: continue

        scanned_history.add(current_url)
        print(f"Scanning: {current_url.replace(base_url, '')} ...", flush=True)

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
                if not href or name in ["Parent Directory", "../", "Name", "Size", "Date"]: continue
                
                full_url = urllib.parse.urljoin(current_url, href)

                if href.endswith("/"):
                    if full_url.startswith(base_url) and full_url not in scanned_history:
                        folders_to_scan.append(full_url)
                elif href.lower().endswith(('.mp4', '.mkv', '.avi')):
                    folder_files.append({"name": name, "url": full_url})

            # --- PROCESS MOVIES ---
            if category == "movies" and folder_files:
                valid = [f for f in folder_files if "sample" not in f['name'].lower()]
                best = valid[0] if valid else folder_files[0]
                
                raw_name = clean_filename(best['name'])
                # ASK IMDB
                meta = get_imdb_metadata(raw_name, "movies")
                
                final_name = meta['name'] if meta else raw_name
                if meta and meta.get('year'): final_name += f" ({meta['year']})"
                
                # CATEGORY LOGIC
                genre = "General" # IMDb API is weak on genres, usually gives "Actor, Movie"
                cat_id = update_category_file("movies", genre, categories)

                s_id = generate_id(final_name)

                print(f"✨ NEW MOVIE: {final_name}", flush=True)
                master_list.append({
                    "stream_id": s_id,
                    "name": final_name,
                    "stream_type": "movie",
                    "stream_icon": meta['stream_icon'] if meta else "",
                    "backdrop_path": meta['backdrop_path'] if meta else [],
                    "rating": meta['rating'] if meta else "0",
                    "added": int(time.time()),
                    "category_id": cat_id,
                    "container_extension": "mp4",
                    "folder_url": current_url,
                    "url": best['url']
                })
                known_folders.add(decoded_current)
                items_since_save += 1

            # --- PROCESS SERIES ---
            elif category == "series" and folder_files:
                series_raw = urllib.parse.unquote(current_url.rstrip('/').split('/')[-1])
                if "Season" in series_raw:
                     series_raw = urllib.parse.unquote(current_url.rstrip('/').split('/')[-2])

                s_id = generate_id(series_raw)
                
                # Check if series exists
                existing = next((s for s in master_list if str(s['series_id']) == str(s_id)), None)
                
                if not existing:
                    # ASK IMDB
                    meta = get_imdb_metadata(series_raw, "series")
                    final_name = meta['name'] if meta else series_raw
                    
                    cat_id = update_category_file("series", "General", categories)
                    
                    print(f"✨ NEW SERIES: {final_name}", flush=True)
                    master_list.append({
                        "series_id": s_id,
                        "name": final_name,
                        "stream_type": "series",
                        "stream_icon": meta['stream_icon'] if meta else "",
                        "rating": meta['rating'] if meta else "0",
                        "added": int(time.time()),
                        "category_id": cat_id,
                        "folder_url": current_url
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
                items_since_save += 1

            if items_since_save >= 20:
                save_json(output_file, master_list)
                if category == "series": save_json(episodes_file, episodes_list)
                items_since_save = 0

        except Exception as e: pass

    save_json(output_file, master_list)
    if category == "series": save_json(episodes_file, episodes_list)
    print(f"\n✅ Finished {category}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['movies', 'series', 'all'], default='all')
    args = parser.parse_args()

    if args.mode in ['movies', 'all']: stealth_scrape(TARGETS[0]) 
    if args.mode in ['series', 'all']: stealth_scrape(TARGETS[1], episodes_file=TARGETS[2]["output"])
