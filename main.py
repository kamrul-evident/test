import discogs_client
import pandas as pd
import time
import logging
from ratelimit import limits, sleep_and_retry
import sys
import os
import re

# Configure logging
logging.basicConfig(
    filename="genre_update.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Discogs API settings
DISCOGS_TOKEN = "wtgBGudBzuGbyRZXXEvYHThvVjRybiiCcpLmTtFX"
RATE_LIMIT = 60  # Requests per minute
PERIOD = 60  # Seconds

# Initialize Discogs client
try:
    discogs = discogs_client.Client("ShopifyGenreUpdater/1.0", user_token=DISCOGS_TOKEN)
    logging.info("Discogs API client initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize Discogs client: {e}")
    sys.exit(1)


# Rate-limited API call
@sleep_and_retry
@limits(calls=RATE_LIMIT, period=PERIOD)
def fetch_genres(release_id):
    try:
        release = discogs.release(release_id)
        genres = release.data.get("genres", [])
        styles = release.data.get("styles", [])
        # Combine genres and styles, remove duplicates
        all_genres = list(set(genres + styles))
        return ", ".join(all_genres) if all_genres else "Unknown"
    except discogs_client.exceptions.HTTPError as e:
        if e.status_code == 404:
            logging.warning(f"Release ID {release_id} not found.")
            return "Not Found"
        elif e.status_code == 429:
            logging.warning("Rate limit exceeded. Waiting...")
            time.sleep(60)
            return fetch_genres(release_id)
        else:
            logging.error(f"API error for release ID {release_id}: {e}")
            return "Error"
    except Exception as e:
        logging.error(f"Unexpected error for release ID {release_id}: {e}")
        return "Error"


def clean_release_id(release_id):
    if pd.isna(release_id):
        return None
    match = re.search(r"\d+", str(release_id))
    return match.group(0) if match else None


def process_csv(input_file, output_file):
    try:
        # Check if input file exists
        if not os.path.exists(input_file):
            logging.error(f"Input file {input_file} does not exist.")
            return False

        # Read CSV with low_memory=False to avoid DtypeWarning
        df = pd.read_csv(input_file, low_memory=False)
        logging.info(f"Loaded CSV: {input_file}, {len(df)} rows.")

        # Ensure the genres column exists
        if "Genres (product.metafields.custom.genres)" not in df.columns:
            df["Genres (product.metafields.custom.genres)"] = ""

        # Process rows with Discogs IDs
        discogs_column = "Discogs (product.metafields.custom.discogs)"
        if discogs_column not in df.columns:
            logging.error(f"Discogs column not found in {input_file}.")
            return False

        total_rows = len(df[discogs_column].dropna())
        processed = 0
        for index, row in df.iterrows():
            release_id = row[discogs_column]
            if pd.notna(release_id):
                processed += 1
                if processed % 100 == 0:
                    logging.info(f"Processed {processed}/{total_rows} rows.")
                release_id = clean_release_id(release_id)
                if not release_id:
                    logging.warning(
                        f"Invalid or missing release ID {release_id} at index {index}."
                    )
                    df.at[index, "Genres (product.metafields.custom.genres)"] = (
                        "Invalid ID"
                    )
                    continue
                logging.info(f"Processing release ID {release_id} at index {index}.")
                genres = fetch_genres(release_id)
                df.at[index, "Genres (product.metafields.custom.genres)"] = genres
                logging.info(f"Updated genres for release ID {release_id}: {genres}")

        # Save updated CSV with UTF-8 encoding
        df.to_csv(output_file, index=False, encoding="utf-8")
        logging.info(f"Saved updated CSV: {output_file}")
        return True
    except Exception as e:
        logging.error(f"Error processing CSV {input_file}: {e}")
        return False


def main():
    # List of CSV files
    csv_files = [
        # ("RR-products_export_1.csv", "output_csv_1.csv"),
        ("RR-products_export_2.csv", "output_csv_2.csv"),
        ("RR-products_export_3.csv", "output_csv_3.csv"),
    ]

    for input_file, output_file in csv_files:
        logging.info(f"Starting processing for {input_file}")
        success = process_csv(input_file, output_file)
        if not success:
            logging.error(f"Failed to process {input_file}")
        else:
            logging.info(f"Successfully processed {input_file}")


if __name__ == "__main__":
    main()
