import xml.etree.ElementTree as ET
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ==========================================
# 1. SETUP PATH & FOLDER
# ==========================================
# Path to file 09.meta4
meta4_file = r"D:\Michael_Thesis\data\09.meta4"

# Folder to save .tif files
download_dir = r"D:\Michael_Thesis\data\dem"

os.makedirs(download_dir, exist_ok=True)

# ==========================================
# 2. UNPACK FILE META4
# ==========================================
print(f"Unpacking {meta4_file}...")
tree = ET.parse(meta4_file)
root = tree.getroot()

namespace = {'metalink': 'urn:ietf:params:xml:ns:metalink'}

download_list = []

# Find all tag <file> in XML
for file_node in root.findall('metalink:file', namespace):
    file_name = file_node.attrib.get('name')

    # Get first URL
    url_node = file_node.find('metalink:url', namespace)
    if url_node is not None and file_name:
        download_list.append({
            'name': file_name,
            'url': url_node.text
        })

print(f"{len(download_list):,} .tif files found need to be downloaded!")


# ==========================================
# 3. SINGLE DOWNLOADER FUNCTION
# ==========================================
def download_tile(item):
    file_path = os.path.join(download_dir, item['name'])

    # Skip if file exists (in case of run stopped)
    if os.path.exists(file_path):
        return True

    try:
        # Download stream (chunking) to secure RAM
        with requests.get(item['url'], stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        return item['name']  # Return failed files' names


# ==========================================
# 4. EXECUTE PARALLEL DOWNLOAD (MULTI-THREAD)
# ==========================================
print("Download started...")

failed_downloads = []

# Use of 10 threads
with ThreadPoolExecutor(max_workers=10) as executor:
    # Display progress bar
    futures = {executor.submit(download_tile, item): item for item in download_list}

    for future in tqdm(as_completed(futures), total=len(download_list), desc="Downloading TIFs"):
        result = future.result()
        if result is not True:
            failed_downloads.append(result)

# ==========================================
# 5. REPORTING
# ==========================================
print("\n=========================================")
print("Download progress done!")
print(f"Downloaded to: {download_dir}.")
if failed_downloads:
    print(f"There are {len(failed_downloads)} files failed to download.")
    print("Suggestion: Re-Run script.")
print("=========================================")