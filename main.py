import streamlit as st
import ee
import requests
import os
import zipfile
import io

# Set up the page configuration
st.set_page_config(page_title="Latur SMAP Downloader", layout="wide")
st.title("Latur SMAP Downloader")

# Authenticate using service account credentials from Streamlit secrets
service_account = st.secrets["earthengine"]["service_account"]
private_key = st.secrets["earthengine"]["private_key"]

credentials = ee.ServiceAccountCredentials(service_account, key_data=private_key)
ee.Initialize(credentials, project="ee-ashutosh10615")
st.success("Earth Engine Initialized using service account credentials.")

# User inputs
start_date = st.text_input("Enter start date (YYYY-MM-DD):", "2025-01-01")
end_date = st.text_input("Enter end date (YYYY-MM-DD):", "2025-01-03")
band_choice = st.selectbox("Select SMAP band(s):", ["surface", "rootzone", "both"])

# Fixed folder name "data"
folder_name = "data"

if st.button("Download SMAP Data"):
    # Create the folder if it doesn't exist
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        st.info(f"Created folder: {folder_name}")

    # Retrieve Latur boundary from FAO GAUL 2015 Level 2
    gaul = ee.FeatureCollection("FAO/GAUL/2015/level2")
    latur_feature = ee.Feature(gaul.filter(ee.Filter.And(
        ee.Filter.eq("ADM0_NAME", "India"),
        ee.Filter.eq("ADM2_NAME", "Latur")
    )).first())
    latur_geometry = latur_feature.geometry()

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

            # Clip the image to the Latur boundary
            clipped_image = selected_image.clip(latur_geometry)

            # Define download parameters for the GeoTIFF
            download_params = {
                'scale': 1000,
                'region': latur_geometry.getInfo()['coordinates'],
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
