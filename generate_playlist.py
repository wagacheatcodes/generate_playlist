import requests
from bs4 import BeautifulSoup
import json
import re

# CONFIGURATION
SOURCE_URL = "https://a.111477.xyz/" # Ensure this URL is the root folder you want to scan
MAX_SIZE_GB = 5.5
OUTPUT_MOVIES = "movies.json"
OUTPUT_SERIES = "series.json"

def get_size_in_gb(size_str):
    """Converts size strings (e.g., '500 MB', '2.1 GB') to float GB"""
    size_str = size_str.upper().replace(',', '')
    try:
        if 'GB' in size_str:
            return float(re.search(r"([\d\.]+)", size_str).group(1))
        elif 'MB' in size_str:
            return float(re.search(r"([\d\.]+)", size_str).group(1)) / 1024
        elif 'KB' in size_str:
            return float(re.search(r"([\d\.]+)", size_str).group(1)) / 1024 / 1024
    except:
        return 0
    return 0

def scrape_directory(url):
    items = []
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # This selector depends on the specific directory theme (Nginx/Apache)
        # Standard Apache/Nginx often use <a> tags and a size column
        links = soup.find_all('a')
        
        for link in links:
            href = link.get('href')
            name = link.text.strip()
            
            # Skip parent directory links
            if href in ['../', './', '/'] or name == 'Parent Directory':
                continue

            # Attempt to find size in the text following the link or in the row
            # This part often requires adjustment based on the exact HTML of the site
            # For simple Open Directories, size is often in the text node after the link
            # We will use a generic approach here:
            
            full_url = url + href if not href.startswith('http') else href
            
            # Simple file extension check for video
            if href.endswith(('.mp4', '.mkv', '.avi')):
                # Try to find size in the row text (common in ODs)
                row_text = link.parent.text if link.parent else "" 
                # If parent is just a TD, look at the next TD (common in table layouts)
                if not row_text or len(row_text) < len(name) + 5:
                     # Look for next sibling element
                     next_elem = link.find_next('td') # Try table cell
                     if next_elem: row_text += " " + next_elem.text
                
                # Extract size
                # This regex looks for patterns like "1.2 GB" or "500 MB"
                size_match = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB|KB)", str(link.parent) + str(link.find_next('td')))
                
                file_size = 0
                if size_match:
                    size_str = f"{size_match.group(1)} {size_match.group(2)}"
                    file_size = get_size_in_gb(size_str)

                # FILTER LOGIC: ≤ 5.5GB
                if 0.1 < file_size <= MAX_SIZE_GB: # 0.1GB min to avoid samples
                    print(f"[ADDED] {name} ({file_size:.2f} GB)")
                    items.append({
                        "name": name,
                        "url": full_url,
                        "image": "", # Open Directories don't usually have images
                        "category_id": "1" # Default category
                    })
                else:
                    print(f"[SKIPPED] {name} ({file_size:.2f} GB - Too large or small)")

            elif href.endswith('/'):
                 # Recursive scan for folders (Series)
                 # WARNING: Recursive scanning can take a long time. 
                 # Uncomment next line to enable recursion if needed.
                 # items.extend(scrape_directory(full_url))
                 pass

    except Exception as e:
        print(f"Error scraping {url}: {e}")
    
    return items

print("Starting scan...")
movies = scrape_directory(SOURCE_URL + "Movies/") # Adjust path if needed
# series = scrape_directory(SOURCE_URL + "Series/") # Adjust path if needed

# Save to JSON
with open(OUTPUT_MOVIES, 'w') as f:
    json.dump(movies, f, indent=4)

print(f"Done! Saved {len(movies)} movies to {OUTPUT_MOVIES}")
