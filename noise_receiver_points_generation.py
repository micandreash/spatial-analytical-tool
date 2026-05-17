import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
import os

# ==========================================
# 1. SETUP PATHS
# ==========================================
study_area_gpkg = r"D:\Michael_Thesis\data\germany\vg250-ew_12-31.utm32s.gpkg.ebenen\vg250-ew_ebenen_1231\DE_VG250.gpkg"
layer_name = "munich_boundary"

output_dir = r"D:\Michael_Thesis\data\indicators\noise"
os.makedirs(output_dir, exist_ok=True)
output_csv = os.path.join(output_dir, "Receiver points.csv")

# Grid resolution in meters
grid_size = 50

# ==========================================
# 2. LOAD BOUNDARY & GENERATE GRID
# ==========================================
print(f"Loading boundary from: {study_area_gpkg}...")
gdf_boundary = gpd.read_file(study_area_gpkg, layer=layer_name)

# Merge into a single polygon in case there are multiple parts
munich_poly = gdf_boundary.geometry.union_all()

# Get the absolute extremes (Bounding Box)
minx, miny, maxx, maxy = munich_poly.bounds
print(f"Bounding Box bounds: X[{minx:.2f} - {maxx:.2f}], Y[{miny:.2f} - {maxy:.2f}]")

# Create arrays of coordinates stepping by grid_size
x_coords = np.arange(minx, maxx, grid_size)
y_coords = np.arange(miny, maxy, grid_size)

print(f"Generating {(len(x_coords) * len(y_coords)):,} total grid points within Bounding Box...")

# Create Point objects
points = [Point(x, y) for x in x_coords for y in y_coords]
points_gdf = gpd.GeoDataFrame(geometry=points, crs=gdf_boundary.crs)

# ==========================================
# 3. SPATIAL FILTER (THE COOKIE CUTTER)
# ==========================================
print("Filtering points to keep only those exactly inside the Munich administrative boundary...")
# Keep points that intersect with the exact shape of the Munich polygon
points_inside = points_gdf[points_gdf.intersects(munich_poly)]

print(f"Filtered down to {len(points_inside):,} points inside Munich.")

# ==========================================
# 4. EXPORT TO MATSIM FORMAT
# ==========================================
print("Exporting to CSV...")
df_receivers = pd.DataFrame({
    'id': range(1, len(points_inside) + 1),
    'x': points_inside.geometry.x,
    'y': points_inside.geometry.y
})

df_receivers.to_csv(output_csv, index=False)
print(f"Successfully saved to: {output_csv}")