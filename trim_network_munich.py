import xml.etree.ElementTree as ET
import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep
from tqdm import tqdm
import gzip

# ==========================================
# 1. SETUP PATHS
# ==========================================
admin_gpkg_path = r"D:\Michael_Thesis\data\germany\vg250-ew_12-31.utm32s.gpkg.ebenen\vg250-ew_ebenen_1231\DE_VG250.gpkg"
input_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\bavaria_1pct_network.xml.gz"
output_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\munich_1pct_network.xml.gz"

# ==========================================
# 2. EXTRACT MUNICH POLYGON
# ==========================================
print("Loading Munich administrative boundary...")
gdf_admin = gpd.read_file(admin_gpkg_path, layer="vg250_gem")
munich_gdf = gdf_admin[gdf_admin['GEN'] == 'München']

if munich_gdf.empty:
    raise ValueError("Munich boundary not found. Please verify the 'GEN' column in your GPKG.")

munich_polygon = munich_gdf.geometry.union_all()
prepared_munich = prep(munich_polygon)

# ==========================================
# 3. PARSE GZ NETWORK AND IDENTIFY CORE NODES
# ==========================================
print(f"Decompressing and parsing network from {input_network}...")
with gzip.open(input_network, 'rb') as f:
    tree = ET.parse(f)
    root = tree.getroot()

nodes_elem = root.find('nodes')
links_elem = root.find('links')

if nodes_elem is None or links_elem is None:
    raise ValueError("Invalid MATSim network XML: Missing <nodes> or <links> tags.")

print("Identifying core nodes within Munich boundaries...")
core_nodes = set()
all_nodes = nodes_elem.findall('node')

for node in tqdm(all_nodes, desc="Scanning nodes", unit=" nodes"):
    x_str = node.get('x')
    y_str = node.get('y')
    if x_str and y_str:
        x, y = float(x_str), float(y_str)
        if prepared_munich.contains(Point(x, y)):
            core_nodes.add(node.get('id'))

# ==========================================
# 4. FILTER LINKS (INTERSECTION LOGIC)
# ==========================================
print("Filtering links intersecting Munich...")
kept_nodes = set()
valid_links = []
all_links = links_elem.findall('link')

for link in tqdm(all_links, desc="Scanning links", unit=" links"):
    from_id = link.get('from')
    to_id = link.get('to')

    # Keep link if at least one node is inside Munich
    if from_id in core_nodes or to_id in core_nodes:
        kept_nodes.add(from_id)
        kept_nodes.add(to_id)
        valid_links.append(link)

links_elem[:] = valid_links

# ==========================================
# 5. CLEAN UP DANGLING NODES
# ==========================================
print("Cleaning up dangling external nodes...")
valid_nodes = []

for node in tqdm(all_nodes, desc="Filtering dangling nodes", unit=" nodes"):
    if node.get('id') in kept_nodes:
        valid_nodes.append(node)

nodes_elem[:] = valid_nodes

# ==========================================
# 6. EXPORT COMPRESSED TRIMMED NETWORK
# ==========================================
print(f"Compressing and writing network to {output_network}...")

with gzip.open(output_network, 'wt', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write('<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">\n')
    # Write the modified root tree as a unicode string
    f.write(ET.tostring(root, encoding='unicode'))

print("\n--- PROCESS COMPLETED ---")
print(f"Original nodes : {len(all_nodes):,}")
print(f"Retained nodes : {len(kept_nodes):,}")
print(f"Original links : {len(all_links):,}")
print(f"Retained links : {len(valid_links):,}")