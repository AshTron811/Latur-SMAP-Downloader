import streamlit as st
import ee
import requests
import os
import zipfile
import io
import json
import tempfile
import geopandas as gpd

# Set up the page configuration
st.set_page_config(page_title="Latur SMAP Downloader", layout="wide")
st.title("Latur SMAP Downloader")

# Read the JSON key from Streamlit secrets
secret_json = st.secrets["ee_credentials"]["json"]
credentials_dict = json.loads(secret_json)
service_account = credentials_dict["client_email"]

# Create a temporary JSON key file and write the secret JSON to it
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json") as temp_file:
    temp_file.write(secret_json)
    temp_file_path = temp_file.name

# Initialize Earth Engine using the temporary key file
credentials = ee.ServiceAccountCredentials(service_account, temp_file_path)
ee.Initialize(credentials, project="ee-ashutosh10615")
# Remove the temporary file after initialization
os.remove(temp_file_path)
st.success("Earth Engine Initialized using service account credentials.")

# User inputs for date range and band choice
start_date = st.text_input("Enter start date (YYYY-MM-DD):", "2025-01-01")
end_date = st.text_input("Enter end date (YYYY-MM-DD):", "2025-01-03")
band_choice = st.selectbox("Select SMAP band(s):", ["surface", "rootzone", "both"])

# Fixed folder name "data"
folder_name = "data"

# Extract extent from EXTENT.zip
extent_shp = None
zip_file_path = "EXTENT.zip"

if os.path.exists(zip_file_path):
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall("EXTENT")
    
    # Find the shapefile inside the extracted folder
    for file in os.listdir("EXTENT"):
        if file.endswith(".shp"):
            extent_shp = os.path.join("EXTENT", file)
            break
else:
    st.error(f"Could not find {zip_file_path}. Please ensure it is placed in the working directory.")

# Load shapefile and convert to Earth Engine geometry
if extent_shp:
    gdf = gpd.read_file(extent_shp)
    if not gdf.empty:
        latur_geometry = ee.Geometry.Polygon(gdf.geometry[0].exterior.coords)
        st.success("Loaded Latur extent from EXTENT.zip.")
    else:
        st.error("Shapefile is empty. Please check EXTENT.zip.")
else:
    st.error("No shapefile found in EXTENT.zip.")

# Add buffer to the extent (e.g., 5000 meters)
extended_geometry = latur_geometry.buffer(5000)

if st.button("Download SMAP Data"):
    # Create the folder if it doesn't exist
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        st.info(f"Created folder: {folder_name}")

    # Retrieve SMAP data for the specified date range
    smap_collection = ee.ImageCollection("NASA/SMAP/SPL4SMGP/007").filterDate(start_date, end_date)
    collection_size = smap_collection.size().getInfo()
    if collection_size == 0:
        st.error(f"No SMAP data available from {start_date} to {end_date}.")
    else:
        st.write(f"Found {collection_size} image(s) in the specified date range.")
        smap_list = smap_collection.toList(collection_size)

        progress_bar = st.progress(0)
        for i in range(collection_size):
            # Get the current SMAP image and its original name (system:index)
            image = ee.Image(smap_list.get(i))
            image_id = image.get("system:index").getInfo()

            # Select the requested band(s)
            if band_choice == 'surface':
                selected_image = image.select("sm_surface")
            elif band_choice == 'rootzone':
                selected_image = image.select("sm_rootzone")
            elif band_choice == 'both':
                selected_image = image.select(["sm_surface", "sm_rootzone"])
            else:
                st.error("Invalid band selection. Please try again.")
                break

            # Instead of clipping to the exact Latur boundary, clip to the extended geometry
            clipped_image = selected_image.clip(extended_geometry)

            # Define download parameters for the GeoTIFF using the extended geometry region
            download_params = {
                'scale': 1000,
                'region': extended_geometry.getInfo()['coordinates'],
                'crs': 'EPSG:4326',
                'fileFormat': 'GeoTIFF'
            }

            # Get the download URL and download the file
            download_url = clipped_image.getDownloadURL(download_params)
            response = requests.get(download_url)
            filename = os.path.join(folder_name, f"{image_id}.tif")
            with open(filename, 'wb') as f:
                f.write(response.content)
            st.write(f"Downloaded {filename}")
            progress_bar.progress((i + 1) / collection_size)
        st.success("Download complete!")

        # Zip all downloaded files for local download
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for file in os.listdir(folder_name):
                file_path = os.path.join(folder_name, file)
                zip_file.write(file_path, arcname=file)
        zip_buffer.seek(0)
        st.download_button(
            label="Download all files as ZIP",
            data=zip_buffer,
            file_name="latur_smap_data.zip",
            mime="application/zip"
        )
