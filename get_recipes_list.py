from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import pandas as pd
import csv
import re
import os

# --- Config ---
PAGE = 1
LIMIT = 1000
LEVEL_MIN = 1
LEVEL_MAX = 99
RACE = ""
CHRONICLE = "lu4"  # ✅ choose: "lu4" or "interlude"

BASE_URL = "https://wiki.mw2.wiki"
INPUT_URL = f"{BASE_URL}/search?query=&type=recipe&sub[levelMin]={LEVEL_MIN}&sub[levelMax]={LEVEL_MAX}&sub[race]={RACE}&page={PAGE}&limit={LIMIT}"
OUTPUT_FILE = "recipes_list.tsv"

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # ✅ enable for headless scraping
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--blink-settings=imagesEnabled=false")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
options.add_argument("--disable-extensions")
options.add_argument("--disable-background-networking")
options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)

print(f"🔍 Loading: {INPUT_URL}")
driver.get(INPUT_URL)
time.sleep(2)  # wait for JS rendering

html = driver.page_source
soup = BeautifulSoup(html, "html.parser")

# --- Parse recipes table ---
recipes = []
rows = soup.select("table.table tbody tr")

for row in rows:
    # icon: filename without extension
    img_tag = row.select_one("img")
    icon = ""
    if img_tag:
        src = img_tag.get("src")
        filename = os.path.basename(src)
        icon = os.path.splitext(filename)[0]

    # link & id
    link_tag = row.select_one("a.item-name")
    href = link_tag.get("href") if link_tag else ""
    full_link = f"{BASE_URL}{href}" if href else ""
    id_match = re.search(r"/item/(\d+)-", href)
    item_id = id_match.group(1) if id_match else ""

    # grade (separate)
    grade_tag = row.select_one(".item-grade")
    grade = grade_tag.get_text(strip=True) if grade_tag else ""

    # name (only the recipe name, excluding grade)
    name_tag = row.select_one(".item-name__content")
    if name_tag:
        # Remove the grade span completely to avoid merging
        grade_span = name_tag.select_one(".item-grade")
        if grade_span:
            grade_span.extract()
        name = name_tag.get_text(strip=True)
    else:
        name = ""

    recipes.append({
        "icon": icon,
        "name": name,
        "id": item_id,
        "grade": grade,
        "link": full_link
    })

driver.quit()

# --- Save to TSV ---
df = pd.DataFrame(recipes)
df.to_csv(
    OUTPUT_FILE,
    sep="\t",
    index=False,
    quoting=csv.QUOTE_NONE,
    escapechar="\\",
    encoding="utf-8"
)

print(f"✅ Done. {len(recipes)} recipes saved to {OUTPUT_FILE}")

# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")
