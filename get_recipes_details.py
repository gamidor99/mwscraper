import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import csv
import re
import json
import html
import os

# --- Config ---
INPUT_FILE = "recipes_list.tsv"
OUTPUT_FILE = "recipes_details.tsv"

WAIT_TIME = 1
OFFSET = 0
LIMIT = 1000  # None = all

BASE_URL = "https://wiki.mw2.wiki"

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")
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

# --- Helper ---
def clean_percent(val):
    if val is None:
        return ""
    return re.sub(r"%", "", str(val)).strip()

# --- Load recipes list ---
recipes_df = pd.read_csv(INPUT_FILE, sep="\t")
if LIMIT is not None:
    recipes_df = recipes_df.iloc[OFFSET:OFFSET + LIMIT]
else:
    recipes_df = recipes_df.iloc[OFFSET:]

print(f"📦 Total recipes to process: {len(recipes_df)} (offset={OFFSET}, limit={LIMIT})")

details = []


for idx, row in recipes_df.iterrows():
    url = row["link"]
    recipe_id = row["id"]
    print(f"🔍 [{idx+1}] Fetching: {url}")

    driver.get(url)
    time.sleep(WAIT_TIME)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # --- Name / Grade ---
    name_tag = soup.select_one("#result-title .item-name__content")
    raw_name = name_tag.get_text(strip=True) if name_tag else ""
    name = re.sub(r"(NG|D|C|B|A|S)$", "", raw_name).strip()

    grade_tag = soup.select_one("#result-title .item-grade")
    grade = grade_tag.get_text(strip=True) if grade_tag else ""

    # --- Description cleanup ---
    desc_tag = soup.select_one("#result-title p")
    description_json = "[]"
    if desc_tag:
        raw_desc = desc_tag.decode_contents()
        raw_desc = html.unescape(raw_desc)
        raw_desc = re.sub(r"<br\s*/?>", "\n", raw_desc, flags=re.I)
        raw_desc = re.sub(r"<[^>]+>", "", raw_desc)
        parts = [p.strip() for p in re.split(r"[\n\r]+", raw_desc) if p.strip()]
        description_json = json.dumps(parts, ensure_ascii=False)

    # --- Item stats ---
    price_npc = weight = olympiad_usable = ""
    restrictions_dict = {}
    stats_rows = soup.select("#result-stats table tr")
    for tr in stats_rows:
        label = tr.select_one("td:first-child").get_text(strip=True)
        value = tr.select_one("td:last-child").get_text(" ", strip=True)
        if "Selling price" in label:
            price_npc = re.sub(r"[^\d]", "", value)
        elif "Weight" in label:
            weight = value
        elif "Olympiad" in label:
            olympiad_usable = value
        elif "Restrictions" in label:
            for span in tr.select("span"):
                text = span.get_text(strip=True)
                key = re.sub(r"[^a-zA-Z0-9]+", "_", text).lower()
                icon = span.select_one("i")
                is_true = "fa-check" in icon.get("class", []) if icon else False
                restrictions_dict[key] = is_true

    # --- Required items (JSON array) ---
    required_items = []
    req_rows = soup.select("h5:contains('Required items') ~ table tr")
    for tr in req_rows:
        link_tag = tr.select_one("a.item-name")
        item_href = link_tag.get("href") if link_tag else ""
        full_link = f"{BASE_URL}{item_href}" if item_href else ""
        item_id_match = re.search(r"/item/(\d+)-", item_href)
        item_id = item_id_match.group(1) if item_id_match else ""

        item_name_tag = tr.select_one(".item-name__content")
        item_name = re.sub(r"(NG|D|C|B|A|S)$", "", item_name_tag.get_text(strip=True)).strip() if item_name_tag else ""

        item_grade_tag = tr.select_one(".item-grade")
        item_grade = item_grade_tag.get_text(strip=True) if item_grade_tag else ""

        qty_td = tr.select_one("td.text-end")
        qty = qty_td.get_text(strip=True) if qty_td else ""

        icon_tag = tr.select_one(".item-icon img")
        icon_src = icon_tag.get("src") if icon_tag else ""
        icon_filename = os.path.splitext(os.path.basename(icon_src))[0] if icon_src else ""

        required_items.append({
            "id": item_id,
            "name": item_name,
            "icon": icon_filename,
            "grade": item_grade,
            "quantity": qty,
            "link": full_link
        })

    # --- Crafting details ---
    craft_level = mp_consumption = result_item_name = result_item_grade = result_quantity = ""
    result_item_id = ""
    result_item_link = ""
    detail_rows = soup.select("h5:contains('Details') ~ table tr")
    for tr in detail_rows:
        label = tr.select_one("td:first-child").get_text(strip=True)
        value_td = tr.select_one("td:last-child")
        value = value_td.get_text(" ", strip=True) if value_td else ""
        if label == "Level":
            craft_level = value
        elif label == "MP Consumption":
            mp_consumption = value
        elif label == "Result":
            res_link_tag = value_td.select_one("a.item-name")
            res_href = res_link_tag.get("href") if res_link_tag else ""
            result_item_link = f"{BASE_URL}{res_href}" if res_href else ""
            match_id = re.search(r"/item/(\d+)-", res_href)
            result_item_id = match_id.group(1) if match_id else ""

            # Name and grade
            res_name_tag = value_td.select_one(".item-name__content")
            if res_name_tag:
                # Extract grade separately
                res_grade_tag = res_name_tag.select_one(".item-grade")
                result_item_grade = res_grade_tag.get_text(strip=True) if res_grade_tag else ""
                if res_grade_tag:
                    res_grade_tag.extract()

                result_item_text = res_name_tag.get_text(" ", strip=True)
                match_qty = re.search(r"x(\d+)", result_item_text)
                result_quantity = match_qty.group(1) if match_qty else ""
                result_item_name = re.sub(r"x\d+", "", result_item_text).strip()
        elif "Chance" in label:
            chance_of_success = clean_percent(value)  # ✅ cleaned

    # --- Drop list ---
    drop_list = []
    for tr in soup.select("#drop tbody tr"):
        link_tag = tr.select_one("a.item-name")
        href = link_tag.get("href") if link_tag else ""
        npc_id_match = re.search(r"/npc/(\d+)-", href)
        npc_id = npc_id_match.group(1) if npc_id_match else ""

        name_tag = tr.select_one(".item-name__content")
        npc_name = name_tag.get_text(" ", strip=True).split("Lv.")[0].strip() if name_tag else ""

        level_tag = tr.select_one(".item-name__additional")
        level_match = re.search(r"Lv\.\s*(\d+)", level_tag.get_text() if level_tag else "")
        npc_level = int(level_match.group(1)) if level_match else None

        amount = tr.select_one("td.text-center").get_text(strip=True) if tr.select_one("td.text-center") else ""
        chance_raw = tr.select_one("td.text-end").get_text(strip=True) if tr.select_one("td.text-end") else ""
        chance = float(clean_percent(chance_raw)) if clean_percent(chance_raw) != "" else 0.0

        drop_list.append({
            "npc": {
                "id": npc_id,
                "name": npc_name,
                "level": npc_level
            },
            "amount": amount,
            "chance": chance
        })

    # --- Spoil list ---
    spoil_list = []
    for tr in soup.select("#spoil tbody tr"):
        link_tag = tr.select_one("a.item-name")
        href = link_tag.get("href") if link_tag else ""
        npc_id_match = re.search(r"/npc/(\d+)-", href)
        npc_id = npc_id_match.group(1) if npc_id_match else ""

        name_tag = tr.select_one(".item-name__content")
        npc_name = name_tag.get_text(" ", strip=True).split("Lv.")[0].strip() if name_tag else ""

        level_tag = tr.select_one(".item-name__additional")
        level_match = re.search(r"Lv\.\s*(\d+)", level_tag.get_text() if level_tag else "")
        npc_level = int(level_match.group(1)) if level_match else None

        amount = tr.select_one("td.text-center").get_text(strip=True) if tr.select_one("td.text-center") else ""
        chance_raw = tr.select_one("td.text-end").get_text(strip=True) if tr.select_one("td.text-end") else ""
        chance = float(clean_percent(chance_raw)) if clean_percent(chance_raw) != "" else 0.0

        spoil_list.append({
            "npc": {
                "id": npc_id,
                "name": npc_name,
                "level": npc_level
            },
            "amount": amount,
            "chance": chance
        })


    details.append({
        "id": recipe_id,
        "name": name,
        "grade": grade,
        "description": description_json,
        "price_npc": price_npc,
        "weight": weight,
        "olympiad_usable": olympiad_usable,
        "restrictions": json.dumps(restrictions_dict, ensure_ascii=False),
        "required_items": json.dumps(required_items, ensure_ascii=False),
        "craft_level": craft_level,
        "mp_consumption": mp_consumption,
        "result_item_name": result_item_name,
        "result_item_grade": result_item_grade,
        "result_item_id": result_item_id,
        "result_item_link": result_item_link,
        "result_quantity": result_quantity,
        "chance_of_success": chance_of_success,
        "drop_list": json.dumps(drop_list, ensure_ascii=False),
        "spoil_list": json.dumps(spoil_list, ensure_ascii=False)
    })

# --- Save to TSV ---
df = pd.DataFrame(details)
df.to_csv(
    OUTPUT_FILE,
    sep="\t",
    index=False,
    quoting=csv.QUOTE_NONE,
    escapechar="\\",
    encoding="utf-8"
)

driver.quit()
print(f"✅ Done. {len(details)} recipe details saved to {OUTPUT_FILE}")

# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")
