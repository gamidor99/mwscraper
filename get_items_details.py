from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import csv
import time
import os
import re
import json
import hashlib

# --- Config ---
INPUT_FILE = "items_list.tsv"
OUTPUT_FILE = "items_details.tsv"
WAIT_TIME = 0.5
MAX_ITEMS = 19900           # None = all
CHECKPOINT_SIZE = 50       # ✅ save progress every 50 items
START_INDEX = 0  # 👈 change this to resume from any row

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
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 15)

# --- Helpers ---
def clean_number(text):
    if text is None:
        return None
    text = str(text).strip()

    # ✅ Remove spaces and non-breaking spaces
    text = text.replace("\u00A0", "").replace(" ", "")

    # ✅ Replace commas with dots if they're decimal separators (rare)
    text = text.replace(",", ".")

    # ✅ Remove thousands separators like 1.104.850 → 1104850
    text = re.sub(r"(?<=\d)\.(?=\d{3}(\D|$))", "", text)

    # ✅ Remove non-digit except dot (for decimals)
    text = re.sub(r"[^\d.]", "", text)

    if text == "":
        return None

    # ✅ Convert to int if possible
    try:
        num = float(text)
        return int(num) if num.is_integer() else num
    except ValueError:
        return None

def slugify_link(url: str) -> str:
    # Works for full URLs or relative paths
    match = re.search(r"/item/([^/]+)/", url)
    if match:
        return match.group(1)  # e.g., "1234-zubeis-breastplate"
    # Fallback: hash the URL if pattern not found
    return hashlib.md5(url.encode()).hexdigest()

def snake_case(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

# --- Load item list ---
df_items = pd.read_csv(INPUT_FILE, sep="\t")
if MAX_ITEMS:
    df_items = df_items.head(MAX_ITEMS)
print(f"📥 Loaded {len(df_items)} items from {INPUT_FILE}")

details = []

# --- Scrape each item ---
for idx, row in df_items.iloc[START_INDEX:].iterrows():
    url = row["link"]
    print(f"[{idx+1}/{len(df_items)}] 🔎 {url}")

    # --- Caching: try loading HTML from cache ---
    chronicle = row["chronicle"] if "chronicle" in df_items.columns else "default"
    slug = slugify_link(url)

    cache_dir = os.path.join("item_details_data", chronicle)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{slug}.html")

    html_source = None

    if os.path.exists(cache_file):
        print(f"📁 Cache hit: {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            html_source = f.read()
    else:
        print(f"🌐 Downloading: {url}")
        driver.get(url)
        time.sleep(WAIT_TIME)
        html_source = driver.page_source
        # ✅ Save to cache
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(html_source)

    # ✅ Parse HTML (from cache or fresh download)
    soup = BeautifulSoup(html_source, "html.parser")






    # --- Basic info ---
    name_tag = soup.select_one("#result-title .item-name__content")
    item_name = name_tag.get_text(strip=True) if name_tag else None

    grade_tag = soup.select_one("#result-title .item-grade")
    grade = grade_tag.get_text(strip=True) if grade_tag else None

    # --- Clean main name (remove grade suffix) ---
    if grade and item_name.endswith(grade):
        item_name = item_name[: -len(grade)].strip()

    # --- Recipes ---
    recipes_json = []
    recipe_row = soup.find("td", string=re.compile(r"Recipes", re.I))
    if recipe_row:
        for recipe_link_tag in recipe_row.find_next("td").select("a.item-name"):
            href = recipe_link_tag.get("href", "")
            recipe_id = None
            match = re.search(r"/item/(\d+)-", href)
            if match:
                recipe_id = int(match.group(1))

            # ✅ Raw name (cleaned)
            raw_name = recipe_link_tag.select_one(".item-name__content").get_text(" ", strip=True) if recipe_link_tag else None
            if raw_name:
                # Clean name
                raw_name = re.sub(r"^Recipe:\s*", "", raw_name, flags=re.IGNORECASE)    # Remove prefix
                raw_name = re.sub(r"\(\d+%?\)", "", raw_name).strip()                   # Remove (60%) / (100%)
                raw_name = re.sub(r"\b(NG|D|C|B|A|S)\b$", "", raw_name).strip()         # Remove trailing grade

            # ✅ Extract chance if available (60%, 100%, etc.)
            chance_match = re.search(r"\((\d+)%\)", recipe_link_tag.get_text())
            recipe_chance = int(chance_match.group(1)) if chance_match else None

            # ✅ Icon
            icon_tag = recipe_link_tag.select_one("img")
            recipe_icon = os.path.splitext(os.path.basename(icon_tag["src"]))[0] if icon_tag else None

            # ✅ Grade
            grade_tag = recipe_link_tag.select_one(".item-grade")
            recipe_grade = grade_tag.get_text(strip=True) if grade_tag else None

            # ✅ Append to list
            recipes_json.append({
                "recipe_id": recipe_id,
                "recipe_name": raw_name,
                "recipe_icon": recipe_icon,
                "recipe_grade": recipe_grade,
                "recipe_chance": recipe_chance,
                "recipe_link": href
            })

    # ✅ Optional: cleanup — if empty list, keep None
    recipes_json = recipes_json if recipes_json else None


    icon_tag = soup.select_one("#result-title .item-icon img")
    icon_url = icon_tag["src"] if icon_tag else ""
    icon_basename = os.path.splitext(os.path.basename(icon_url))[0] if icon_url else None

    # --- Chronicle ---
    chronicle_tag = soup.select_one("#server-tabs .nav-link.active")
    chronicle = chronicle_tag.get_text(strip=True) if chronicle_tag else None


    # --- Stats table ---
    STAT_NAME_MAP = {
        "Шанс Физ. Крит. Атк.": "chance_of_phys_crit_atk",
        "Chance of Phys. Crit. Atk.": "chance_of_phys_crit_atk",
        "P. Atk.": "p_atk",
        "M. Atk.": "m_atk",
        "P.Def.": "p_def",
        "M.Def.": "m_def",
        "Crit. Rate": "crit_rate",
        "Accuracy": "accuracy",
        "Evasion": "evasion",
        "Shield Def.": "shield_defence",   # ✅ match actual key below
        "Shield Rate": "shield_rate",
        "MP Consumption": "mp_consume",
        "Soul/Spiritshot Consumption": "soul_spirit_shots_consumption",
        "Selling price NPC": "selling_price_npc",
        "Weight": "weight",
        # ✅ Add more if you encounter new labels
    }

    # --- Stats table ---
    stats = {}
    for tr in soup.select("#result-stats table tr"):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue

        key_raw = tds[0].get_text(strip=True)
        key = STAT_NAME_MAP.get(key_raw, snake_case(key_raw))
        val_raw = tds[1].get_text(" ", strip=True)

        if key == "item_skills":
            continue

        # ✅ Special handling: Soul/Spiritshot consumption
        if key == "soul_spirit_shots_consumption":
            if "/" in val_raw:
                parts = [p.strip() for p in val_raw.split("/")]
                try:
                    soulshot = int(parts[0]) if int(parts[0]) > 0 else None
                    spiritshot = int(parts[1]) if int(parts[1]) > 0 else None
                except ValueError:
                    soulshot, spiritshot = None, None
            else:
                soulshot, spiritshot = None, None

            stats["soulshot_consumption"] = soulshot
            stats["spiritshot_consumption"] = spiritshot
            continue  # 🚨 Important: skip default handling

        # ✅ Special handling: Shield Defence with percent
        if key == "shield_defence":
            td_html = str(tds[1])  # 🔥 you were missing this variable before
            main_val_match = re.search(r"(\d+)", val_raw)
            if main_val_match:
                stats["shield_defence_value"] = int(main_val_match.group(1))

            percent_match = re.search(r"\(([\d.,]+)%\)", td_html)
            if percent_match:
                stats["shield_defence_percent"] = int(float(percent_match.group(1).replace(",", ".")))
            else:
                stats["shield_defence_percent"] = None

            continue  # ✅ do not add original key

        # ✅ Default handling for all other stats
        val_clean = clean_number(val_raw)
        stats[key] = val_clean if val_clean is not None else val_raw

    # --- Item Skills ---
    item_skills_json = []
    skills_row = soup.find("td", string=re.compile(r"Item skills", re.I))

    if skills_row:
        for a in skills_row.find_next("td").select("a.item-name"):
            skill_link = a.get("href", "")
            
            # ✅ Skill ID
            skill_id = None
            match = re.search(r"/skill/(\d+)-", skill_link)
            if match:
                skill_id = int(match.group(1))

            # ✅ Full text (contains name + grade sometimes)
            name_tag = a.select_one(".item-name__content")
            full_text = name_tag.get_text(" ", strip=True) if name_tag else None

            # ✅ Extract level
            level_match = re.search(r"Lv\.\s*(\d+)", full_text)
            skill_level = int(level_match.group(1)) if level_match else None
            full_text = re.sub(r"Lv\.\s*\d+", "", full_text).strip()

            # ✅ Clean name: remove “(Grade X)” part
            skill_name = re.sub(r"\(Grade\s+[A-D|S\d+]*\)", "", full_text, flags=re.IGNORECASE).strip()

            # ✅ Icon
            icon_tag = a.select_one("img")
            skill_icon = (
                os.path.splitext(os.path.basename(icon_tag["src"]))[0] if icon_tag else None
            )

            item_skills_json.append({
                "id": skill_id,
                "name": skill_name,
                "icon": skill_icon,
                "level": skill_level,
                "link": skill_link
            })

    # ✅ Drop 'recipes' from stats (already parsed separately)
    if "recipes" in stats:
        del stats["recipes"]

    # Example: type_text might be "Weapon / Sword" or "Armor / Heavy"
    type_text = stats.get("type", None)

    main_type, sub_type = None, None
    if type_text and type_text != None:
        parts = [p.strip() for p in type_text.split("/")]
        if len(parts) > 0:
            main_type = parts[0]
        if len(parts) > 1:
            sub_type = parts[1]

    stats["type"] = main_type
    stats["subtype"] = sub_type.strip("{}").lower() if sub_type else None

    # --- Item Description ---
    description_tag = soup.select_one("#result-title div[style*='margin-left'] p")
    item_description = None
    item_description_json = None

    if description_tag:
        # ✅ Replace <br> with newlines
        for br in description_tag.find_all("br"):
            br.replace_with("\n")

        raw_text = description_tag.get_text("\n", strip=True)
        item_description = raw_text if raw_text else None

        effects = []
        stat_type = None
        has_header = False

        for line in [l.strip() for l in raw_text.split("\n") if l.strip()]:
            # ✅ Detect header (<Effects>, <Available Soul Crystals>, etc.)
            if line.startswith("<") and line.endswith(">"):
                stat_type = line.strip("<>").strip()
                has_header = True
                continue

            # ✅ If no header was seen yet — ignore lines
            if not has_header:
                continue

            # ✅ Try "Stat: Value" format
            match = re.match(r"^(.*?):\s*(.*)$", line)
            if match:
                stat_name = match.group(1).strip()
                stat_desc = match.group(2).strip()
            else:
                # ✅ If no colon, just store the full line as description
                stat_name = None
                stat_desc = line

            # ✅ Clean garbage lines (like <font color=...>)
            if stat_desc.lower().startswith("<font"):
                continue

            if stat_desc:
                effects.append({
                    "type": stat_name,
                    "description": stat_desc
                })

        # ✅ Only if a <Header> exists and we collected effects
        if has_header and effects:
            # Filter: remove empty description
            effects = [e for e in effects if e["description"].strip() != ""]
            if effects:
                item_description_json = [{
                    "stat_type": stat_type,
                    "list": effects
                }]
        else:
            item_description_json = None

    # --- Restrictions ---
    restrictions_json = {}

    # Find the specific Restrictions row
    restrictions_row = None
    for tr in soup.select("#result-stats table tr"):
        first_td = tr.find("td")
        if first_td and "Restrictions" in first_td.get_text():
            restrictions_row = tr
            break

    if restrictions_row:
        for span in restrictions_row.select("td span"):
            text = span.get_text(strip=True)
            if not text:
                continue
            key = snake_case(text)
            has_check = bool(span.select_one(".fa-check"))
            restrictions_json[key] = has_check

    # --- Drops ---
    drops_json = []
    for tr in soup.select("#drop table tbody tr"):
        cols = tr.find_all("td")
        if len(cols) == 3:
            npc_cell = cols[0]
            npc_link_tag = npc_cell.select_one("a.item-name")
            npc_link = npc_link_tag["href"] if npc_link_tag else None

            # ✅ Extract NPC ID
            npc_id = None
            if npc_link:
                match = re.search(r"/npc/(\d+)-", npc_link)
                if match:
                    npc_id = int(match.group(1))

            # ✅ Extract NPC name
            npc_name_tag = npc_cell.select_one(".item-name__content")
            npc_name = npc_name_tag.get_text(" ", strip=True) if npc_name_tag else None

            # ✅ Extract Level separately (from item-name__additional)
            npc_level_tag = npc_cell.select_one(".item-name__additional")
            npc_level = None
            if npc_level_tag:
                lvl_match = re.search(r"Lv\.\s*(\d+)", npc_level_tag.get_text(strip=True))
                if lvl_match:
                    npc_level = int(lvl_match.group(1))

            # Clean name (remove level part if it's still inside)
            if npc_name:
                npc_name = re.sub(r"Lv\.\s*\d+", "", npc_name).strip()

            # ✅ Extract Amount
            amount_text = cols[1].get_text(strip=True)
            amount_text = re.sub(r"[^\d\- ]", "", amount_text).strip()
            amount_val = amount_text if amount_text else None

            # ✅ Extract Chance
            chance_text = cols[2].get_text(strip=True).replace("%", "").strip()
            chance_val = clean_number(chance_text)

            drops_json.append({
                "npc_id": npc_id,
                "npc_name": npc_name,
                "npc_level": npc_level,
                "npc_link": npc_link,
                "amount": amount_val,
                "chance": chance_val if chance_val is not None else None
            })



    # --- Crystals ---
    crystals_json = []
    for tr in soup.select("#crystals table tbody tr"):
        cols = tr.find_all("td")
        if len(cols) == 3:
            crystals_json.append({
                "modification": clean_number(cols[0].get_text(strip=True)),
                "crystallization": clean_number(cols[1].get_text(strip=True)),
                "fail": clean_number(cols[2].get_text(strip=True))
            })


    # --- Quest Rewards ---
    quest_rewards_json = []
    for tr in soup.select("#questreward table tbody tr"):
        cols = tr.find_all("td")
        if len(cols) == 2:
            quest_name = cols[0].get_text(" ", strip=True)
            quest_link_tag = cols[0].select_one("a.item-name")
            quest_link = quest_link_tag["href"] if quest_link_tag else None

            # ✅ Extract quest_id from href (e.g. /quest/370-an-elder-sows-seeds/lu4)
            quest_id = None
            if quest_link:
                match = re.search(r"/quest/(\d+)-", quest_link)
                if match:
                    quest_id = int(match.group(1))

            # ✅ Extract level range as integers if possible
            level_text = cols[1].get_text(strip=True)
            level_min, level_max = None, None
            if "~" in level_text:
                parts = [p.strip() for p in level_text.split("~")]
                if len(parts) == 2:
                    level_min = clean_number(parts[0])
                    level_max = clean_number(parts[1])
            else:
                level_min = clean_number(level_text)

            quest_rewards_json.append({
                "quest_id": quest_id,
                "quest_name": quest_name,
                "quest_link": quest_link,
                "level_min": level_min,
                "level_max": level_max
            })


    # --- Quest Goal ---
    quest_goal_json = []
    for tr in soup.select("#questGoal table tbody tr"):
        cols = tr.find_all("td")
        if len(cols) == 2:
            quest_name = cols[0].get_text(" ", strip=True)
            quest_link_tag = cols[0].select_one("a.item-name")
            quest_link = quest_link_tag["href"] if quest_link_tag else None

            # Extract level range
            level_text = cols[1].get_text(strip=True)
            level_min, level_max = None, None
            if "~" in level_text:
                parts = [p.strip() for p in level_text.split("~")]
                if len(parts) == 2:
                    level_min = clean_number(parts[0])
                    level_max = clean_number(parts[1])
            else:
                level_min = clean_number(level_text)

            quest_goal_json.append({
                "quest_name": quest_name,
                "quest_link": quest_link,
                "level_min": level_min,
                "level_max": level_max
            })


    # --- Contained Items ---
    contained_json = []
    for tr in soup.select("#contained table tbody tr"):
        td = tr.find("td")
        if not td:
            continue

        link_tag = td.select_one("a.item-name")
        item_link = link_tag["href"] if link_tag else None

        # ✅ ID from href
        item_id = None
        if item_link:
            match = re.search(r"/item/(\d+)-", item_link)
            if match:
                item_id = int(match.group(1))

        # ✅ Name (pure, without grade)
        raw_name = link_tag.select_one(".item-name__content").get_text(" ", strip=True) if link_tag else None

        # Extract grade from `<span class="item-grade">`
        grade_tag = link_tag.select_one(".item-grade")
        item_grade = grade_tag.get_text(strip=True) if grade_tag else None

        # Clean the name (remove grade text if included at the end)
        if item_grade != None and raw_name.endswith(item_grade):
            raw_name = raw_name[: -len(item_grade)].strip()

        # ✅ Icon (basename)
        icon_tag = td.select_one("img")
        icon = os.path.splitext(os.path.basename(icon_tag["src"]))[0] if icon_tag else None

        # ✅ Chance value inside `(xxxxxx)`
        chance_match = re.search(r"\(([\d.,]+)\)", td.get_text())
        chance_val = clean_number(chance_match.group(1)) if chance_match else None

        contained_json.append({
            "id": item_id,
            "name": raw_name,
            "grade": item_grade,
            "icon": icon,
            "chance": chance_val,
            "link": item_link
        })

    # --- Soul Crystals ---
    soul_crystals_json = []
    soul_row = soup.find("td", string=re.compile(r"Soul Crystals", re.I))

    if soul_row:
        container = soul_row.find_next("td")
        for block in container.select("div.collapser > div"):
            # --- Augmentation item (main) ---
            main_link_tag = block.select_one("a.item-name")
            if not main_link_tag:
                continue

            main_href = main_link_tag.get("href", "")
            main_id_match = re.search(r"/item/(\d+)-", main_href)
            main_id = int(main_id_match.group(1)) if main_id_match else None

            main_name_tag = main_link_tag.select_one(".item-name__content")
            main_name = main_name_tag.get_text(" ", strip=True) if main_name_tag else None

            # Effect is in <span class="item-name__additional">
            effect_tag = main_link_tag.select_one(".item-name__additional")
            effect = effect_tag.get_text(strip=True) if effect_tag else None

            # Grade
            grade_tag = main_link_tag.select_one(".item-grade")
            main_grade = grade_tag.get_text(strip=True) if grade_tag else None

            # Icon
            icon_tag = main_link_tag.select_one("img")
            main_icon = os.path.splitext(os.path.basename(icon_tag["src"]))[0] if icon_tag else None

            # --- Materials (next sibling <div style="margin...">) ---
            materials_json = []
            material_container = block.find_next_sibling("div")
            if material_container:
                for mat_link in material_container.select("a.item-name"):
                    mat_href = mat_link.get("href", "")
                    mat_id_match = re.search(r"/item/(\d+)-", mat_href)
                    mat_id = int(mat_id_match.group(1)) if mat_id_match else None

                    mat_name_tag = mat_link.select_one(".item-name__content")
                    mat_name = mat_name_tag.get_text(" ", strip=True) if mat_name_tag else None

                    mat_grade_tag = mat_link.select_one(".item-grade")
                    mat_grade = mat_grade_tag.get_text(strip=True) if mat_grade_tag else None

                    mat_icon_tag = mat_link.select_one("img")
                    mat_icon = os.path.splitext(os.path.basename(mat_icon_tag["src"]))[0] if mat_icon_tag else None

                    # Extract amount if available: (555 pcs)
                    mat_amount_match = re.search(r"\(([\d,\.]+)\s*pcs\)", mat_name)
                    mat_amount = int(mat_amount_match.group(1)) if mat_amount_match else None

                    materials_json.append({
                        "id": mat_id,
                        "name": mat_name,
                        "icon": mat_icon,
                        "link": mat_href,
                        "grade": mat_grade,
                        "amount": mat_amount
                    })

            soul_crystals_json.append({
                "augmentation_item": {
                    "id": main_id,
                    "name": main_name,
                    "icon": main_icon,
                    "link": main_href,
                    "effect": effect,
                    "grade": main_grade
                },
                "materials": materials_json
            })

    # --- Set ---
    set_json = []
    set_row = soup.find("td", string=re.compile(r"Set part", re.I))
    if set_row:
        for a in set_row.find_next("td").select("a.item-name"):
            set_link = a.get("href", "")
            set_id = None
            match = re.search(r"/set/(\d+)-", set_link)
            if match:
                set_id = int(match.group(1))

            set_name_tag = a.select_one(".item-name__content")
            set_name = set_name_tag.get_text(" ", strip=True) if set_name_tag else None

            # ✅ PvP flag before cleaning
            pvp = True if "{PvP}" in (set_name or "") else False

            if set_name:
                # Remove {PvP}
                set_name = set_name.replace("{PvP}", "")
                # Remove “– Set” or "- Set" or "–Set"
                set_name = re.sub(r"[\-–]\s*Set", "", set_name, flags=re.IGNORECASE)
                # Remove trailing grade letters (NG, D, C, B, A, S) if present
                set_name = re.sub(r"\s*\b(NG|D|C|B|A|S)\b$", "", set_name, flags=re.IGNORECASE)
                # Remove double spaces
                set_name = re.sub(r"\s+", " ", set_name).strip()

            # ✅ Icon
            icon_tag = a.select_one("img")
            set_icon = os.path.splitext(os.path.basename(icon_tag["src"]))[0] if icon_tag else None

            # ✅ Grade
            grade_tag = a.select_one(".item-grade")
            set_grade = grade_tag.get_text(strip=True) if grade_tag else None

            # ✅ Class (Foundation, etc.)
            class_tag = a.select_one(".item-class")
            set_class = class_tag.get_text(strip=True) if class_tag else None

            set_json.append({
                "set_id": set_id,
                "set_name": set_name,
                "set_icon": set_icon,
                "set_grade": set_grade,
                "set_class": set_class,
                "set_full_link": set_link,
                "pvp": pvp
            })


    # ✅ Clean up: remove invalid/empty sets
    set_json = [
        s for s in set_json 
        if not (
            s["set_id"] is None and 
            (not s["set_name"] or s["set_name"].strip() == "") and 
            s["set_icon"] is None and 
            s["set_grade"] is None
        )
    ]



    # --- Append result ---
    details.append({
        "item_id": row["id"],
        "item_name": item_name,
        "item_grade": grade,
        "item_icon": icon_basename,

        "item_description": item_description,
        "item_description_json": json.dumps(item_description_json, ensure_ascii=False) if item_description_json else None,

        "item_skills": json.dumps(item_skills_json, ensure_ascii=False) if item_skills_json else None,
        "item_set": json.dumps(set_json, ensure_ascii=False) if set_json else None,

        "chronicle": chronicle,

        **stats,

        #"recipe_id": recipe_id,
        #"recipe_name": recipe_name,
        #"recipe_icon": recipe_icon,
        #"recipe_grade": recipe_grade,

        "recipes": json.dumps(recipes_json, ensure_ascii=False) if recipes_json else None,

        "link": url,

        "restrictions": json.dumps(restrictions_json, ensure_ascii=False) if restrictions_json else None,
        "drops": json.dumps(drops_json, ensure_ascii=False) if drops_json else None,
        "quest_rewards": json.dumps(quest_rewards_json, ensure_ascii=False) if quest_rewards_json else None,
        "quest_goal": json.dumps(quest_goal_json, ensure_ascii=False) if quest_goal_json else None,
        "contained": json.dumps(contained_json, ensure_ascii=False) if contained_json else None,
        "crystals": json.dumps(crystals_json, ensure_ascii=False) if crystals_json else None,
        "soul_crystals": json.dumps(soul_crystals_json, ensure_ascii=False) if soul_crystals_json else None,
    })

    # ✅ Save checkpoint every N items
    if (idx + 1) % CHECKPOINT_SIZE == 0:
        checkpoint_file = OUTPUT_FILE.replace(".tsv", f"_checkpoint.tsv")
        pd.DataFrame(details).to_csv(checkpoint_file, sep="\t", index=False, quoting=csv.QUOTE_MINIMAL)
        print(f"💾 Checkpoint saved: {checkpoint_file}")

driver.quit()

# --- Save TSV ---
df_out = pd.DataFrame(details)

# ✅ Convert all null-like values to "Null" only for export
df_out = df_out.fillna("Null")
df_out = df_out.replace(["", "nan", "NaN", None], "Null")

# --- Convert numeric columns to int or Null ---
numeric_cols = [
    "item_id",
    "p_atk",
    "m_atk",
    "selling_price_npc",
    "weight",
    "mp_consume",
    "p_def",
    "m_def",
    "crit_rate",
    "accuracy",
    "evasion",
    "shield_defence_value",
    "shield_defence_percent",
    "shield_rate",
    "chance_of_phys_crit_atk",
    "soulshot_consumption",
    "spiritshot_consumption"
]

for col in numeric_cols:
    if col in df_out.columns:
        df_out[col] = (
            df_out[col]
            .replace(["Null", "", None], 0)       # unify nulls as 0 first
            .fillna(0)
            .astype(str)
            .str.replace(r"[^\d\.-]", "", regex=True)  # strip non-numeric
            .replace("", 0)
            .astype(float)
            .round(0)
            .astype("Int64")                      # ✅ keep nullable integer type
        )

        # 🔥 Replace 0 with Null (pd.NA)
        df_out[col] = df_out[col].replace(0, pd.NA)

columns_json = json.dumps(df_out.columns.tolist(), indent=4)
print(columns_json)

ordered_columns = [
    "item_id",
    "item_name",
    "item_grade",
    "item_icon",
    "item_skills",
    "item_description",
    "item_description_json",
    "item_set",

    "chronicle",
    "type",
    "subtype",
    "link",
    "p_atk",
    "m_atk",
    "accuracy",
    "crit_rate",
    "evasion",
    "p_def",
    "m_def",
    "shield_defence_value",
    "shield_defence_percent",
    "shield_rate",
    "chance_of_phys_crit_atk",
    "soulshot_consumption",
    "spiritshot_consumption",
    "mp_consume",
    "selling_price_npc",
    "weight",    

    "can_it_be_used_at_the_olympiad",
    "restrictions",

    #"recipe_id",
    #"recipe_name",
    #"recipe_icon",
    #"recipe_grade",

    "recipes",
    
    "drops",
    "quest_rewards",
    "quest_goal",
    "contained",
    "crystals"
]

# ✅ Reorder columns safely
#df_out = df_out[[c for c in ordered_columns if c in df_out.columns]]

df_out.to_csv(OUTPUT_FILE, sep="\t", index=False, quoting=csv.QUOTE_MINIMAL)
print(f"\n💾 Saved {len(df_out)} item details to {OUTPUT_FILE}")

# --- GUI viewer ---
try:
    from pandasgui import show
    print("📊 Opening GUI...")
    show(df_out)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

#input("\n✅ Done. Press Enter to exit...")
