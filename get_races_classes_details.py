import os
import re
import json
import time
import argparse
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from deep_translator import GoogleTranslator

# --- Config ---
INPUT_FILE = "data/races_classes/races_lu4.tsv"
OUTPUT_FILE = "data/races_classes/races_details_lu4.tsv"
CACHE_DIR = "cache/classes_details"
BASE_URL = "https://wikipedia1.mw2.wiki"
WAIT_TIME = 3
LIMIT = 12

# --- CLI Arguments ---
parser = argparse.ArgumentParser(description="Scrape and cache race/class detail pages by chronicle, with stats.")
parser.add_argument("--limit", type=int, default=LIMIT, help="Limit entries to process (default: 12)")
args = parser.parse_args()
LIMIT = args.limit

# --- Helpers ---
def clean_url(url: str) -> str:
    return re.sub(r'\?.*$', '', url)

def tr(text: str) -> str:
    if not text or text.strip() == "":
        return text
    try:
        return GoogleTranslator(source="auto", target="en").translate(text)
    except Exception:
        return text

def safe_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]+', '_', name)

def extract_stats_from_html(html: str):
    """Extract stats and class JSON data from HTML source."""
    stats = []
    class_data = []
    scripts = re.findall(r"<script.*?>.*?</script>", html, re.S)
    for script in scripts:
        # --- Extract stat data array ---
        match = re.search(r"data\s*:\s*\[\s*([\d,\s]+)\s*\]", script)
        if match:
            stats = [int(x.strip()) for x in match.group(1).split(",") if x.strip().isdigit()]
        # --- Extract JSON with class data ---
        json_match = re.search(r"window\._classData\s*=\s*(\[.*?\]);", script, re.S)
        if json_match:
            json_text = json_match.group(1)
            try:
                class_data = json.loads(json_text)
            except json.JSONDecodeError:
                try:
                    class_data = eval(json_text.replace("null", "None").replace("true", "True").replace("false", "False"))
                except Exception:
                    class_data = []
        if stats or class_data:
            break
    return stats, class_data

# --- Selenium setup ---
options = Options()
# options.add_argument("--headless")  # Uncomment for headless mode
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
options.add_argument("--disable-extensions")
options.add_argument("--disable-background-networking")
options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)

# --- Read TSV ---
df_input = pd.read_csv(INPUT_FILE, sep="\t")
print(f"📖 Loaded {len(df_input)} entries from {INPUT_FILE}")
if LIMIT < len(df_input):
    df_input = df_input.head(LIMIT)
    print(f"⚙️ Processing only first {LIMIT} entries.")

rows = []

# --- Main Loop ---
for idx, row in df_input.iterrows():
    link = str(row["subtype_link"])
    race_name = str(row["race_name"])
    subtype_name = str(row["subtype_name"])
    chronicle = str(row["chronicle"])
    server_id = str(row["server_id"])

    chron_dir = os.path.join(CACHE_DIR, chronicle)
    os.makedirs(chron_dir, exist_ok=True)
    cache_file = os.path.join(chron_dir, f"{safe_filename(race_name)}_{safe_filename(subtype_name)}.html")

    print(f"[{idx+1}/{len(df_input)}] 🌐 {race_name} / {subtype_name}")

    html_source = ""
    if os.path.exists(cache_file):
        print(f"💾 Loading from cache → {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            html_source = f.read()
    else:
        print(f"🔎 Fetching from web → {link}")
        try:
            driver.get(link)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#class-heading h1")))
            time.sleep(WAIT_TIME)  # only sleep when fetching new page
            html_source = driver.page_source
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(html_source)
            print(f"✅ Cached → {cache_file}")
        except Exception as e:
            print(f"⚠️ Error loading {link}: {e}")
            continue

    # --- Parse HTML ---
    soup = BeautifulSoup(html_source, "html.parser")

    # --- Extract heading ---
    heading_el = soup.select_one("#class-heading h1")
    class_name = heading_el.get_text(strip=True) if heading_el else ""
    race_icon_el = heading_el.select_one("img") if heading_el else None
    race_icon = clean_url(BASE_URL + race_icon_el["src"]) if race_icon_el else ""

    # --- Extract description ---
    desc_el = soup.select_one("#class-desc__text")
    class_description = desc_el.get_text(" ", strip=True) if desc_el else ""
    class_description_en = tr(class_description)

    # --- Extract summary table ---
    summary = {}
    for tr_el in soup.select("#class-summary__table tr"):
        key_el = tr_el.select_one("td b")
        val_el = tr_el.select("td")
        if key_el and len(val_el) >= 2:
            key = key_el.get_text(strip=True).rstrip(":")
            value = val_el[1].get_text(" ", strip=True)
            summary[key.lower()] = value

    role = tr(summary.get("role", ""))
    weapon = tr(summary.get("weapon", ""))
    armor = tr(summary.get("armor", ""))

    # --- Extract right-side image ---
    class_image_el = soup.select_one("#class-image img")
    class_image = clean_url(BASE_URL + class_image_el["src"]) if class_image_el else ""

    # --- Extract stats ---
    stats, class_data = extract_stats_from_html(html_source)
    STR, DEX, CON, INT, WIT, MEN = (stats + [None] * 6)[:6]  # pad to ensure 6 columns

    # --- Save data row ---
    rows.append({
        "race_name": race_name,
        "subtype_name": subtype_name,
        "class_name": class_name,
        "race_icon": race_icon,
        "class_image": class_image,
        "description_ru": class_description,
        "description_en": class_description_en,
        "role": role,
        "weapon": weapon,
        "armor": armor,
        "STR": STR,
        "DEX": DEX,
        "CON": CON,
        "INT": INT,
        "WIT": WIT,
        "MEN": MEN,
        "chronicle": chronicle,
        "server_id": server_id,
        "link": link
    })

    print(f"📊 Stats: STR={STR}, DEX={DEX}, CON={CON}, INT={INT}, WIT={WIT}, MEN={MEN}")

# --- Save results ---
df_out = pd.DataFrame(rows)
df_out.to_csv(OUTPUT_FILE, sep="\t", index=False)
print(f"✅ Saved {len(df_out)} details with stats to {OUTPUT_FILE}")

# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(df_out)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

driver.quit()
print("🏁 Done.")
