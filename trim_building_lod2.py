import os
import shutil
import xml.etree.ElementTree as ET
import geopandas as gpd
from shapely.geometry import box
from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
study_area_gpkg = r"D:\Michael_Thesis\data\germany\vg250-ew_12-31.utm32s.gpkg.ebenen\vg250-ew_ebenen_1231\DE_VG250.gpkg"
layer_name = "munich_boundary"

gml_source_dir = r"D:\Michael_Thesis\data\bavaria\buildings LoD2"

gml_strict_dir = r"D:\Michael_Thesis\data\bavaria\buildings LoD2_munich_trial 2"
os.makedirs(gml_strict_dir, exist_ok=True)

# ==========================================
# 2. GET EXACT STUDY AREA POLYGON
# ==========================================
print(f"Loading exact administrative boundary from: {study_area_gpkg}...")
gdf_boundary = gpd.read_file(study_area_gpkg, layer=layer_name)

# Exact Munich administrative boundary shape (not bounding box)
munich_poly = gdf_boundary.geometry.union_all()

# ==========================================
# 3. SCAN & STRICT FILTER GML FILES
# ==========================================
print("\nStarting scan of GML files (reading headers only)...")
gml_files = [f for f in os.listdir(gml_source_dir) if f.endswith('.gml')]
matched_files = 0

ns = {'gml': 'http://www.opengis.net/gml'}

for file_name in tqdm(gml_files, desc="Filtering GMLs strictly"):
    file_path = os.path.join(gml_source_dir, file_name)

    try:
        context = ET.iterparse(file_path, events=('end',))
        for event, elem in context:
            if 'boundedBy' in elem.tag:
                lower_corner = elem.find('.//gml:lowerCorner', ns)
                upper_corner = elem.find('.//gml:upperCorner', ns)

                if lower_corner is not None and upper_corner is not None:
                    lx, ly = map(float, lower_corner.text.split()[:2])
                    ux, uy = map(float, upper_corner.text.split()[:2])

                    gml_box = box(lx, ly, ux, uy)

                    if munich_poly.intersects(gml_box):
                        shutil.copy2(file_path, os.path.join(gml_strict_dir, file_name))
                        matched_files += 1

                break
    except Exception as e:
        pass

print(f"\nStrict scan complete! Found {matched_files} GML files that intersect the actual Munich boundary.")
print(f"Files copied to: {gml_strict_dir}")