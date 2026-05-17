import glob
from osgeo import gdal

def build_vrt_from_tifs(tif_folder, output_vrt):
    print("Searching .tifs' folder...")

    # Get all .tifs' path in the folder
    search_path = f"{tif_folder}\\*.tif"
    tif_list = glob.glob(search_path)

    if not tif_list:
        print(".tifs not found. Check folder path")
        return

    print(f"{len(tif_list):,} .tif files found. Building virtual raster...")

    # Execute virtual raster construction
    vrt_options = gdal.BuildVRTOptions(resampleAlg='nearest')
    gdal.BuildVRT(output_vrt, tif_list, options=vrt_options)

    print(f"Virtual raster construction finished! File saved in: {output_vrt}")

# ==========================================
# EXECUTION
# ==========================================

folder_tifs = r"D:\Michael_Thesis\data\dem"
file_vrt = r"D:\Michael_Thesis\data\dem\dem_vrt.vrt"

build_vrt_from_tifs(folder_tifs, file_vrt)