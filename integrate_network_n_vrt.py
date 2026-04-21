import xml.etree.ElementTree as ET
import rasterio
import math

def inject_elevation_to_network(network_in, network_out, vrt_path):
    print("Loading network.xml into RAM...")
    # Parsing full XML
    tree = ET.parse(network_in)
    root = tree.getroot()

    # Strip invisible XML namespaces to prevent ElementTree blind spots
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]

    # --- Phase 1: Extract Nodes and Coordinates ---
    print("Extracting Nodes...")
    nodes_dict = {}

    # Use .iter() to recursively find all 'node' tags anywhere in the tree
    for node in root.iter('node'):
        nid = node.get('id')
        x = float(node.get('x'))
        y = float(node.get('y'))
        nodes_dict[nid] = {'x': x, 'y': y, 'z': 0.0}  # Default 0.0

    # Prepare a list of coordinate tuples to query the raster
    coords = [(n['x'], n['y']) for n in nodes_dict.values()]
    node_ids = list(nodes_dict.keys())

    # --- Phase 2: Batch elevation query from VRT ---
    print(f"Querying Z elevations from {vrt_path} for {len(coords):,} nodes...")

    with rasterio.open(vrt_path) as src:
        # rasterio.sample extracts values for all coordinates in a single vectorized operation
        z_values = src.sample(coords)

        for nid, z_val in zip(node_ids, z_values):
            z = z_val[0]

            # Fallback logic: Assign Z = 0.0 for nodes outside the Bavaria boundary (NoData)
            if z == src.nodata or z < -9999 or math.isnan(z):
                z = 0.0

            nodes_dict[nid]['z'] = z

    # --- Phase 3: Calculate gradients and update links ---
    print("Calculating gradients and updating links...")

    for link in root.iter('link'):
        from_id = link.get('from')
        to_id = link.get('to')
        length = float(link.get('length'))

        # Safety check: ensure both from_id and to_id exist in our nodes dictionary
        if from_id in nodes_dict and to_id in nodes_dict:
            length = float(link.get('length'))

            z_from = nodes_dict[from_id]['z']
            z_to = nodes_dict[to_id]['z']

            gradient = 0.0
            if length > 0:
                gradient = (z_to - z_from) / length

            # Locate the <attributes> container
            attrs = link.find('attributes')
            if attrs is None:
                attrs = ET.SubElement(link, 'attributes')

            # Inject z_from, z_to, gradient
            attr_zfrom = ET.SubElement(attrs, 'attribute', name="z_from", attrib={'class': 'java.lang.Double'})
            attr_zfrom.text = str(round(z_from, 3))

            attr_zto = ET.SubElement(attrs, 'attribute', name="z_to", attrib={'class': 'java.lang.Double'})
            attr_zto.text = str(round(z_to, 3))

            attr_grad = ET.SubElement(attrs, 'attribute', name="gradient", attrib={'class': 'java.lang.Double'})
            attr_grad.text = str(round(gradient, 5))

    # --- Phase 4: Create new network.xml ---
    print(f"Saving new 3D network to {network_out}...")

    with open(network_out, 'wb') as f:
        # 1. Force the XML declaration to be on the very first line
        f.write(b"<?xml version='1.0' encoding='utf-8'?>\n")

        # 2. Write the DOCTYPE right below it
        doctype = '<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">\n'
        f.write(doctype.encode('utf-8'))

        # 3. Write the rest of the network tree (tell it NOT to print the declaration again)
        tree.write(f, encoding="utf-8", xml_declaration=False)

    print("3D network created!")


# ==========================================
# Execution
# ==========================================
input_xml = r"D:\Michael_Thesis\data\eqasim_population_bavaria\bavaria_1pct_network.xml\bavaria_1pct_network.xml"
output_xml = r"D:\Michael_Thesis\data\eqasim_population_bavaria\bavaria_1pct_network.xml\bavaria_1pct_network_3d.xml"
vrt_file = r"D:\Michael_Thesis\data\dem\dem_vrt.vrt"

inject_elevation_to_network(input_xml, output_xml, vrt_file)