from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import time
import csv
import re
import json

# --- Config ---
INPUT_FILE = "data/quests_list.tsv"
OUTPUT_FILE = "data/quests_details.tsv"

CHRONICLE = "lu4"    # ✅ e.g., "lu4", "interlude", "gracia-final", "high-five"
LIMIT = 9999           # ✅ how many quests to scrape (None = all)
WAIT_TIME = 1        # ✅ seconds to wait for each page to load

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # ❌ uncomment for headless mode
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

def clean_icon_name(src: str) -> str:
    if not src:
        return ""
    filename = src.split("/")[-1]         # e.g. "etc_crest_yellow_i00.png"
    return filename.replace(".png", "")   # ✅ "etc_crest_yellow_i00"

# --- Read quest list ---
quests_df = pd.read_csv(INPUT_FILE, sep="\t", encoding="utf-8")

# ✅ Apply limit
if LIMIT is not None and LIMIT < len(quests_df):
    quests_df = quests_df.head(LIMIT)

print(f"📜 Total quests to scrape: {len(quests_df)} (Chronicle: {CHRONICLE})")

details = []

for idx, row in quests_df.iterrows():
    quest_id = row["ID"]
    quest_name = row["Name"]
    original_url = row["Link"]

    # ✅ Create a clean URL-safe slug
    slug = quest_name.lower()
    slug = slug.replace(" ", "-")
    slug = slug.replace("’", "").replace("'", "")  # remove apostrophes
    slug = re.sub(r"[^a-z0-9\-]", "", slug)       # 🔥 remove ? ! , . etc.

    url = re.sub(
        r"/quest/[^/]+/[^/]+$",
        f"/quest/{quest_id}-{slug}/{CHRONICLE}",
        original_url
    )

    print(f"🔎 [{idx+1}/{len(quests_df)}] Scraping: {quest_name} ({url})")
    driver.get(url)
    time.sleep(WAIT_TIME)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # --- Title ---
    title_tag = soup.select_one("#result-title .item-name__content")
    name = title_tag.get_text(strip=True) if title_tag else quest_name

    # --- Short description ---
    desc_tag = soup.select_one("#result-title p")
    description = desc_tag.get_text(strip=True) if desc_tag else ""

    # --- Start NPC ---
    start_npc_id = None
    start_npc_name = None
    start_npc_additional = None
    start_npc_icon = None

    start_npc_tag = soup.find("td", string=re.compile("Start NPC", re.I))
    if start_npc_tag:
        npc_cell = start_npc_tag.find_next_sibling("td")
        npc_link = npc_cell.select_one("a.item-name")

        # ✅ Extract ID from href (/npc/30554-bolter/eternal)
        if npc_link:
            href = npc_link.get("href", "")
            m = re.search(r"/npc/(\d+)-", href)
            if m:
                start_npc_id = m.group(1)

        # ✅ Extract main name
        name_tag = npc_cell.select_one(".item-name__content")
        if name_tag and name_tag.contents:
            # First text node is the name before <span class="item-name__additional">
            start_npc_name = name_tag.contents[0].strip()

        # ✅ Extract additional title (if exists)
        additional_tag = npc_cell.select_one(".item-name__additional")
        if additional_tag:
            start_npc_additional = additional_tag.get_text(strip=True)

        # ✅ Extract and clean icon name
        icon_tag = npc_cell.select_one("img")
        if icon_tag:
            src = icon_tag.get("src", "")
            filename = src.split("/")[-1]  # e.g. "skill4416_dwarf.png"
            start_npc_icon = filename.replace(".png", "")  # ✅ "skill4416_dwarf"

    # --- Location (multiple spawn points) ---
    spawn_points = []
    for sp in soup.select(".spawn-point"):
        if "style" in sp.attrs:
            style = sp["style"]
            top_match = re.search(r"top:\s*([\d\.]+)px", style)
            left_match = re.search(r"left:\s*([\d\.]+)px", style)
            if top_match and left_match:
                spawn_points.append({
                    "top": float(top_match.group(1)),
                    "left": float(left_match.group(1))
                })

    location_json = json.dumps(spawn_points, ensure_ascii=False)

    # --- Level ---
    level_min, level_max = None, None
    level_row = soup.find("td", string=re.compile("Level", re.I))
    if level_row:
        lvl_text = level_row.find_next_sibling("td").get_text(strip=True)
        m = re.search(r"(\d+)\s*~\s*(\d+)", lvl_text)
        if m:
            level_min, level_max = m.groups()

    # --- Rewards ---
    rewards_list = []
    reward_rows = soup.find_all("a", class_="item-name")
    for r in reward_rows:
        # Only parse those inside the reward section
        parent_td = r.find_parent("td")
        if parent_td and "Награды" in parent_td.find_previous_sibling("td").get_text():
            name_tag = r.select_one(".item-name__content")
            icon_tag = r.select_one("img")
            icon_name = clean_icon_name(icon_tag.get("src")) if icon_tag else ""
            grade_tag = r.select_one(".item-grade")

            rewards_list.append({
                "name": name_tag.get_text(strip=True) if name_tag else "",
                "icon": icon_name,
                "grade": grade_tag.get_text(strip=True) if grade_tag else ""
            })

    rewards_json = json.dumps(rewards_list, ensure_ascii=False)

    # --- Steps (JSON structured) ---
    steps_list = []

    for idx, step_header in enumerate(soup.select("#quest-row h5"), start=1):
        raw_title = step_header.get_text(strip=True)

        # ✅ Clean title (remove 1:, 2:, etc.)
        title = re.sub(r"^\d+\s*:\s*", "", raw_title).strip()

        # ✅ Description
        desc_tag = step_header.find_next_sibling("div")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # ✅ Initialize containers
        npc_data = None
        item_data = None

        # --- Find all <a class="item-name"> links within this step's section ---
        step_links = step_header.find_all_next("a", class_="item-name", limit=5)

        for link in step_links:
            href = link.get("href", "")

            # --- NPC ---
            if href.startswith("/npc/"):
                npc_id = None
                npc_name = None
                npc_additional = None
                npc_icon = None

                m = re.search(r"/npc/(\d+)-", href)
                if m:
                    npc_id = m.group(1)

                name_tag = link.select_one(".item-name__content")
                if name_tag and name_tag.contents:
                    npc_name = name_tag.contents[0].strip()

                add_tag = link.select_one(".item-name__additional")
                if add_tag:
                    npc_additional = add_tag.get_text(strip=True)

                icon_tag = link.select_one("img")
                if icon_tag:
                    src = icon_tag.get("src", "")
                    filename = src.split("/")[-1]
                    npc_icon = filename.replace(".png", "")

                npc_data = {
                    "id": npc_id,
                    "name": npc_name,
                    "additional": npc_additional,
                    "icon": npc_icon
                }

            # --- ITEM ---
            elif href.startswith("/item/"):
                item_id = None
                item_name = None
                item_icon = None
                item_grade = None

                # ✅ ID
                m = re.search(r"/item/(\d+)-", href)
                if m:
                    item_id = m.group(1)

                # ✅ Name
                name_tag = link.select_one(".item-name__content")
                if name_tag:
                    item_name = name_tag.get_text(strip=True)

                # ✅ Grade
                grade_tag = link.select_one(".item-grade")
                if grade_tag:
                    item_grade = grade_tag.get_text(strip=True)

                # ✅ Clean name (remove grade text from the end if it's stuck)
                if item_grade and item_name and item_name.endswith(item_grade):
                    item_name = item_name[: -len(item_grade)].strip()

                # ✅ Icon
                icon_tag = link.select_one("img")
                if icon_tag:
                    src = icon_tag.get("src", "")
                    filename = src.split("/")[-1]
                    item_icon = filename.replace(".png", "")

                item_data = {
                    "id": item_id,
                    "name": item_name,
                    "icon": item_icon,
                    "grade": item_grade
                }

        # ✅ Append step JSON object
        steps_list.append({
            "number": idx,
            "title": title,
            "description": description,
            "npc": npc_data,
            "item": item_data
        })

    steps_json = json.dumps(steps_list, ensure_ascii=False)






    details.append({
        "id": quest_id,
        "name": name,
        "description": description,

        "start_npc_id": start_npc_id,
        "start_npc_name": start_npc_name,
        "start_npc_additional": start_npc_additional,
        "start_npc_icon": start_npc_icon,

        "location": location_json,
        "level_min": level_min,
        "level_max": level_max,
        "rewards": rewards_json,
        "steps": steps_json,
        "chronicle": CHRONICLE,     # ✅ included in dataset
        "link": url
    })

driver.quit()

# --- Save results ---
details_df = pd.DataFrame(details)
print("\n📊 Sample scraped data:")
print(details_df.head())

details_df.to_csv(
    OUTPUT_FILE,
    sep="\t",
    index=False,
    quoting=csv.QUOTE_NONE,
    escapechar="\\",      # ✅ added escape character
    encoding="utf-8"
)

print(f"\n✅ Detailed quest data saved to: {OUTPUT_FILE}")

# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(details_df)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

# --- Exit ---
input("🔚 Press Enter to exit...")
