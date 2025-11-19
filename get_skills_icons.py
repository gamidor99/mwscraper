# --- Config ---
import os
import time
import pandas as pd
import requests
from urllib.parse import urljoin

INPUT_FILE = "data/skills/skills_list_eternal.tsv"
ICON_BASE_URL = "https://wikipedia1.mw2.wiki/icon64/"
SAVE_DIR = "data/skills/icons"

WAIT_TIME = 0.5        # Wait between attempts
LIMIT = 1009999            # Default number of skills to process
OFFSET = 0             # Start row index
RETRY_COUNT = 3        # Retry count per icon

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}

# --------------------------------------------------------
# Ensure output directory exists
# --------------------------------------------------------
os.makedirs(SAVE_DIR, exist_ok=True)

# --------------------------------------------------------
# Load TSV and normalize headers (critical on macOS)
# --------------------------------------------------------
skills_df = pd.read_csv(INPUT_FILE, sep="\t")

skills_df.columns = (
    skills_df.columns
    .str.replace(r"[\ufeff\u200b\u200c\u200d\xa0]", "", regex=True)  # remove BOM + zero-width
    .str.strip()  # remove whitespace around column names
)

# Debug once (optional)
# print("Columns detected:", skills_df.columns.tolist())

# --------------------------------------------------------
# Apply OFFSET + LIMIT
# --------------------------------------------------------
skills_df = skills_df.iloc[OFFSET : OFFSET + LIMIT]
print(f"Loaded {len(skills_df)} skills (OFFSET={OFFSET}, LIMIT={LIMIT})")


# --------------------------------------------------------
# Download helper function
# --------------------------------------------------------
def download_icon(icon_name: str):
    """Downloads icon_name.png unless it already exists."""

    if not icon_name or not str(icon_name).strip():
        return

    icon_name = str(icon_name).strip()
    filename = f"{icon_name}.png"
    save_path = os.path.join(SAVE_DIR, filename)

    # Skip if already downloaded and valid filesize
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        print(f"✔ Already exists, skipping: {filename}")
        return

    url = urljoin(ICON_BASE_URL, filename)

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)

            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(r.content)
                print(f"Downloaded: {filename}")
                break
            else:
                print(f"❌ HTTP {r.status_code} for {filename} "
                      f"(attempt {attempt}/{RETRY_COUNT})")

        except Exception as e:
            print(f"❌ Error downloading {filename} "
                  f"(attempt {attempt}/{RETRY_COUNT}): {e}")

        # Retry delay (except last attempt)
        if attempt < RETRY_COUNT:
            time.sleep(WAIT_TIME)

    # Global sleep between icons
    time.sleep(WAIT_TIME)


# --------------------------------------------------------
# Main loop
# --------------------------------------------------------
print("\nStarting icon download...\n")

for idx, row in skills_df.iterrows():

    icon_main  = row.get("skill_icon", "")
    icon_panel = row.get("skill_icon_panel", "")

    # Download main icon
    if str(icon_main).strip():
        download_icon(str(icon_main).strip())

    # Download panel icon (if any)
    if str(icon_panel).strip():
        download_icon(str(icon_panel).strip())

print("\n✔ Done! Icons processed with retry + offset + limit + sleep\n")
