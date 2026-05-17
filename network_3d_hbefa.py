import xml.etree.ElementTree as ET
import geopandas as gpd
from shapely.geometry import LineString
import rasterio
from tqdm import tqdm
import math
import pandas as pd
import gzip

# ==========================================
# 1. CONFIGURATION
# ==========================================
input_xml = r"D:\Michael_Thesis\data\eqasim_population_bavaria\munich_1pct_network_connected.xml.gz"
output_xml = r"D:\Michael_Thesis\data\eqasim_population_bavaria\munich_1pct_network_connected_3d_hbefa.xml.gz"
dem_raster_path = r"D:\Michael_Thesis\data\dem\dem_vrt.vrt"
admin_gpkg_path = r"D:\Michael_Thesis\data\germany\vg250-ew_12-31.utm32s.gpkg.ebenen\vg250-ew_ebenen_1231\DE_VG250.gpkg"
csv_path = r"D:\Michael_Thesis\data\hbefa\EFA_HOT_Vehcat_reformat.csv"

# ==========================================
# 2. EXTRACT NODES DIRECTLY
# ==========================================
print("Decompressing and parsing XML network...", flush=True)

with gzip.open(input_xml, 'rt', encoding='utf-8') as f:
    tree = ET.parse(f)
    root = tree.getroot()

# Strip namespaces if any exist to prevent blind spots
for elem in root.iter():
    if '}' in elem.tag:
        elem.tag = elem.tag.split('}', 1)[1]

nodes_dict = {}
for node in tqdm(root.iter('node'), desc="Extracting nodes"):
    nodes_dict[node.get('id')] = {'x': float(node.get('x')), 'y': float(node.get('y')), 'z': 0.0}

# ==========================================
# 3. DEM INTEGRATION (THE "SILENT" FAST WAY)
# ==========================================
node_ids = list(nodes_dict.keys())
coords = [(n['x'], n['y']) for n in nodes_dict.values()]

print(f"Sampling DEM data for {len(coords):,} nodes...")
print(">>> WARNING: Console will pause here for a few minutes. Rasterio is working in the background. DO NOT STOP IT! <<<")

FALLBACK_Z_TEXT = "Node falls outside DEM data"

with rasterio.open(dem_raster_path) as src:
    z_values = list(src.sample(coords))

    for i, nid in enumerate(tqdm(node_ids, desc="Assigning elevations to nodes")):
        z = float(z_values[i][0])
        # Fallback logic for outside bounds or NoData
        if z == src.nodata or z < -9000 or math.isnan(z):
            nodes_dict[nid]['z'] = FALLBACK_Z_TEXT
        else:
            nodes_dict[nid]['z'] = z

#%%
# ==========================================
# 4. SPATIAL JOIN USING MULTI-POINT SAMPLING
# ==========================================
# sample_points = []
# for link in tqdm(root.iter('link'), desc="Generating multi-point samples (5 pts/link)"):
#     f_id = link.get('from')
#     t_id = link.get('to')
#
#     if f_id in nodes_dict and t_id in nodes_dict:
#         x1, y1 = nodes_dict[f_id]['x'], nodes_dict[f_id]['y']
#         x2, y2 = nodes_dict[t_id]['x'], nodes_dict[t_id]['y']
#         line = LineString([(x1, y1), (x2, y2)])
#
#         for fraction in [0.1, 0.3, 0.5, 0.7, 0.9]:
#             pt = line.interpolate(fraction, normalized=True)
#             sample_points.append({
#                 'link_id': link.get('id'),
#                 'geometry': pt
#             })
#
# gdf_samples = gpd.GeoDataFrame(sample_points, crs="EPSG:25832")
#
# print("Loading administrative boundaries...")
# gdf_admin = gpd.read_file(admin_gpkg_path, layer="vg250_gem")[['BEZ', 'geometry']]
#
# print("Performing spatial join on sample points...")
# if gdf_samples.crs != gdf_admin.crs:
#     gdf_admin = gdf_admin.to_crs(gdf_samples.crs)
#
# gdf_joined = gpd.sjoin(gdf_samples, gdf_admin, how="left", predicate="intersects")
#
# print("Determining dominant spatial context (Majority Vote)...")
#
#
# def get_dominant_bez(group):
#     # Filter dulu baris yang BEZ-nya NaN (yang jatuh di luar batas)
#     valid_bez = group.dropna(subset=['BEZ'])
#
#     if valid_bez.empty:
#         return None # Biarkan kosong kalau nggak ada titik yang masuk poligon
#
#     return valid_bez['BEZ'].mode().iloc[0]
#
#
# tqdm.pandas(desc="Aggregating majority vote per link")
# spatial_context_dict = gdf_joined.groupby('link_id').progress_apply(get_dominant_bez).to_dict()

# ==========================================
# 4. EXACT SPATIAL JOIN USING INTERSECTION LENGTH
# ==========================================
lines_data = []

for link in tqdm(root.iter('link'), desc="Creating LineStrings for exact intersection"):
    f_id = link.get('from')
    t_id = link.get('to')

    if f_id in nodes_dict and t_id in nodes_dict:
        x1, y1 = nodes_dict[f_id]['x'], nodes_dict[f_id]['y']
        x2, y2 = nodes_dict[t_id]['x'], nodes_dict[t_id]['y']
        lines_data.append({
            'link_id': link.get('id'),
            'geometry': LineString([(x1, y1), (x2, y2)])
        })

gdf_links = gpd.GeoDataFrame(lines_data, crs="EPSG:25832")

print("Loading administrative boundaries...")
gdf_admin = gpd.read_file(admin_gpkg_path, layer="vg250_gem")[['BEZ', 'geometry']]

if gdf_links.crs != gdf_admin.crs:
    gdf_admin = gdf_admin.to_crs(gdf_links.crs)

print("Performing exact length-based spatial intersection... (This may take a while)")
gdf_intersected = gpd.overlay(gdf_links, gdf_admin, how='intersection')

print("Calculating lengths of intersected segments...")
# Rounding to 3 decimal places (millimeters) to avoid floating-point precision errors during tie detection
gdf_intersected['intersected_length'] = gdf_intersected.geometry.length.round(3)

print("Validating edge cases for identical segment lengths...")
# Identify maximum length for each link
max_lengths = gdf_intersected.groupby('link_id')['intersected_length'].transform('max')

# Filter segments that match the maximum length
max_segments = gdf_intersected[gdf_intersected['intersected_length'] == max_lengths]

# Count how many max length segments exist per link
tie_counts = max_segments.groupby('link_id').size()

# Extract link_ids that have more than 1 max length segment (a tie)
tied_links = tie_counts[tie_counts > 1].index.tolist()

if tied_links:
    raise ValueError(f"Execution halted: Found exact length ties for the following link_ids: {tied_links}")

print("Determining dominant spatial context based on maximum length...")
gdf_dominant = gdf_intersected.sort_values(by=['link_id', 'intersected_length'], ascending=[True, False])
gdf_dominant = gdf_dominant.drop_duplicates(subset=['link_id'], keep='first')

spatial_context_dict = dict(zip(gdf_dominant['link_id'], gdf_dominant['BEZ']))

print(f"Successfully mapped {len(spatial_context_dict)} links.")

# %%
# ==========================================
# 5. HBEFA MAPPING AND XML INJECTION (CLEANED)
# ==========================================
df_hbefa = pd.read_csv(csv_path, sep=';', encoding='utf-8')

# Extract available combinations. Output example: {'RUR/Local': set(60, 80), 'URB/Access': set(30, 50)}
available_combinations = {}
for ts in df_hbefa['TrafficSit'].unique():
    parts = str(ts).split('/')
    if len(parts) >= 3:
        ctx_cat = f"{parts[0]}/{parts[1]}"
        spd_str = parts[2].replace('>', '')  # Handle case >130
        try:
            spd = int(spd_str)
            if ctx_cat not in available_combinations:
                available_combinations[ctx_cat] = set()
            available_combinations[ctx_cat].add(spd)
        except:
            pass

valid_gradients = [-6, -4, -2, 0, 2, 4, 6]

def inject_attr(attrs_elem, name, java_class, value):
    new_attr = ET.SubElement(attrs_elem, 'attribute', {'name': name, 'class': java_class})
    new_attr.text = str(value)

for link in tqdm(root.iter('link'), desc="Applying HBEFA & injecting attributes"):
    link_id = link.get('id')
    f_id = link.get('from')
    t_id = link.get('to')

    if f_id in nodes_dict and t_id in nodes_dict:
        length = float(link.get('length', 0.0))
        freespeed = float(link.get('freespeed', 0.0))

        # 1. Context
        bez_type = str(spatial_context_dict.get(link_id, "Gemeinde")).strip()
        context = "URB" if bez_type == "Stadt" else "RUR"

        # 2. Highway Category
        highway_type = "access"
        attrs = link.find('attributes')

        if attrs is None:
            attrs = ET.SubElement(link, 'attributes')
        else:
            # CLEANUP: Remove old attributes to prevent duplicates in RAM
            for tag in ['z_from', 'z_to', 'gradient', 'GRADIENT', 'hbefa_road_type']:
                for old_attr in attrs.findall(f"./attribute[@name='{tag}']"):
                    attrs.remove(old_attr)

            for attr in attrs.findall('attribute'):
                if attr.get('name') == 'osm:way:highway':
                    highway_type = attr.text if attr.text else "access"
                    break

        hw = highway_type.lower()
        if hw in ['motorway', 'motorway_link']:
            road_category = "MW"
        elif hw in ['primary', 'primary_link', 'trunk', 'trunk_link']:
            road_category = "Trunk"
        elif hw in ['secondary', 'secondary_link']:
            road_category = "Distr"
        elif hw in ['unclassified', 'tertiary', 'tertiary_link']:
            road_category = "Local"
        else:
            road_category = "Access"

        # Force specific Urban road categories to match HBEFA city types
        if context == "URB" and road_category == "MW":
            road_category = "MW-City"
        elif context == "URB" and road_category == "Trunk":
            road_category = "Trunk-City"

        # 3. Discretization
        if math.isinf(freespeed):
            speed_kmh = 130
        else:
            speed_kmh = round(freespeed * 3.6)

        ctx_cat = f"{context}/{road_category}"
        valid_speeds = list(available_combinations[ctx_cat])
        closest_speed = min(valid_speeds, key=lambda x: abs(x - speed_kmh))
        speed_str = ">130" if (road_category == "MW" and closest_speed >= 130) else str(closest_speed)

        # 4. Gradient Logic
        z_from = nodes_dict[f_id]['z']
        z_to = nodes_dict[t_id]['z']
        gradient = 0.0

        if not (isinstance(z_from, str) or isinstance(z_to, str)) and length > 0:
            gradient = (z_to - z_from) / length

        grad_pct = round(gradient * 100)
        closest_gradient = min(valid_gradients, key=lambda x: abs(x - grad_pct))

        if closest_gradient > 0:
            grad_str = f"+{closest_gradient}%"
        else:
            grad_str = f"{closest_gradient}%"

        # 5. STRING FORMATTING
        hbefa_string = f"{context}/{road_category}/{speed_str}/{grad_str}"
        noise_gradient_pct = round(gradient * 100, 2)

        # 6. XML Injection
        z_from_class = "java.lang.String" if isinstance(z_from, str) else "java.lang.Double"
        z_to_class = "java.lang.String" if isinstance(z_to, str) else "java.lang.Double"

        z_from_val = z_from if isinstance(z_from, str) else round(z_from, 3)
        z_to_val = z_to if isinstance(z_to, str) else round(z_to, 3)

        inject_attr(attrs, 'z_from', z_from_class, z_from_val)
        inject_attr(attrs, 'z_to', z_to_class, z_to_val)
        inject_attr(attrs, 'gradient', 'java.lang.Double', round(gradient, 5))
        inject_attr(attrs, 'GRADIENT', 'java.lang.Double', noise_gradient_pct)
        inject_attr(attrs, 'hbefa_road_type', 'java.lang.String', hbefa_string)

# %%
# ==========================================
# 6. EXPORT
# ==========================================
def indent(elem, level=0):
    """Function to add spaces/tabs for human-readable XML"""
    i = "\n" + level * "\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

indent(root)

print(f"Compressing and exporting to: {output_xml}", flush=True)

with gzip.open(output_xml, 'wt', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write('<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">\n')
    f.write(ET.tostring(root, encoding='unicode'))

print("Pipeline execution completed successfully.", flush=True)