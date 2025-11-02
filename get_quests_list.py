from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import pandas as pd
import csv
import re

# --- Config ---
PAGE = 1       # ✅ which page to scrape
LIMIT = 9999     # ✅ how many results per page

BASE_URL = "https://wiki.mw2.wiki"
INPUT_URL = f"{BASE_URL}/search/quest?query=&sub[levelMin]=1&sub[levelMax]=99&sub[race]=&page={PAGE}&limit={LIMIT}"
OUTPUT_FILE = f"data/quests_list.tsv"

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # ❌ uncomment if you want headless
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

# ⚡ Performance optimizations
options.add_argument("--blink-settings=imagesEnabled=false")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
options.add_argument("--disable-extensions")
options.add_argument("--disable-background-networking")
options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)

# --- Open page ---
print(f"🌐 Loading page: {INPUT_URL}")
driver.get(INPUT_URL)
time.sleep(3)  # wait for content to load

# --- Parse HTML ---
soup = BeautifulSoup(driver.page_source, "html.parser")

quests = []
for a in soup.select("a.item-name"):
    href = a.get("href", "")
    full_link = BASE_URL + href if href.startswith("/") else href

    name_tag = a.select_one(".item-name__content")
    name = name_tag.contents[0].strip() if name_tag else None

    # Extract level range
    level_tag = a.select_one(".item-name__additional")
    level_text = level_tag.get_text(strip=True) if level_tag else ""

    # Extract min and max levels using regex
    level_min, level_max = None, None
    match = re.search(r"(\d+)\s*~\s*(\d+)", level_text)
    if match:
        level_min, level_max = match.groups()

    # Extract quest ID from href
    quest_id = None
    if "/quest/" in href:
        quest_id = href.split("/quest/")[1].split("-")[0]

    quests.append({
        "ID": quest_id,
        "Name": name,
        "LevelMin": level_min,
        "LevelMax": level_max,
        "Link": full_link
    })

driver.quit()

# --- Create DataFrame ---
df = pd.DataFrame(quests)
print("\n📊 DataFrame Preview:")
print(df.head())

# --- Save to TSV ---
df.to_csv(
    OUTPUT_FILE,
    sep="\t",           # ✅ tab-separated
    index=False,
    quoting=csv.QUOTE_NONE,
    encoding="utf-8"
)

print(f"\n✅ TSV saved to: {OUTPUT_FILE}")

# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

# --- Exit ---
input("🔚 Press Enter to exit...")
