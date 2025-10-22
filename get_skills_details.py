# --- Config ---
import time, re, pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os
import json

INPUT_FILE = "skills_list.tsv"
OUTPUT_FILE = "skills_details.tsv"
WAIT_TIME = 0.5  # seconds between requests
LIMIT = 999500     # how many skills to scrape per run
OFFSET = 0     # start from this index (0-based)

# --- Directory for HTML cache ---
CACHE_DIR = "skills_details_data"

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

# --- Helper: convert to snake_case ---
def to_snake_case(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

# --- Load skill list ---
skills_df = pd.read_csv(INPUT_FILE, sep="\t")

# Apply offset and limit
skills_df = skills_df.iloc[OFFSET : OFFSET + LIMIT]
print(f"Loaded {len(skills_df)} skills (OFFSET={OFFSET}, LIMIT={LIMIT})")

results = []

# --- Scrape each skill ---
for i, row in skills_df.iterrows():
    skill_id = row["skill_id"]
    skill_name = row["skill_name"]
    skill_icon = row["skill_icon"]
    skill_link = row["skill_link"]
    chronicle = row["chronicle"]

    # Ensure directory structure exists
    os.makedirs(CACHE_DIR, exist_ok=True)
    chronicle_dir = os.path.join(CACHE_DIR, chronicle)
    os.makedirs(chronicle_dir, exist_ok=True)

    print(f"[{i+1+OFFSET}] Scraping: {skill_name} ({skill_link})")

    try:
        # --- Cache system for main skill page ---
        safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", skill_name.lower()).strip("_")
        main_cache_path = os.path.join(chronicle_dir, f"{safe_name}_{skill_id}_main.html")

        # Load from cache or fetch online
        if os.path.exists(main_cache_path):
            print(f"📂 Main cache found for {skill_name} → {main_cache_path}")
            with open(main_cache_path, "r", encoding="utf-8") as f:
                html_source = f.read()
        else:
            print(f"🌐 Fetching main skill page: {skill_name}")
            driver.get(skill_link)
            time.sleep(WAIT_TIME)
            html_source = driver.page_source
            with open(main_cache_path, "w", encoding="utf-8") as f:
                f.write(html_source)
            print(f"💾 Saved main page cache → {main_cache_path}")

        soup = BeautifulSoup(html_source, "html.parser")

        # --- Extract top info ---
        result_div = soup.select_one("div#result-title")
        if not result_div:
            print("⚠️ Missing main info, skipping.")
            continue

        # icon, name, level, description
        icon_src = result_div.select_one("img")["src"] if result_div.select_one("img") else ""
        name_text = result_div.select_one(".item-name__content").get_text(" ", strip=True) if result_div.select_one(".item-name__content") else skill_name
        skill_level = result_div.select_one(".item-name__additional").get_text(" ", strip=True) if result_div.select_one(".item-name__additional") else ""
        skill_description = result_div.select_one("div p").get_text(" ", strip=True) if result_div.select_one("div p") else ""

        # --- Extract all skill levels (if available) ---
        level_table = soup.select_one("table.table-stripped.table-vcenter")
        if level_table:
            print(f"🔍 Found multiple levels for {skill_name}:")
            level_links = []
            for tr in level_table.select("tr"):
                a_tag = tr.select_one("a.item-name")
                desc_td = tr.select("td")[1] if len(tr.select("td")) > 1 else None
                if not a_tag:
                    continue

                href = a_tag["href"].strip()
                level_text = a_tag.select_one(".item-name__additional")
                level_raw = level_text.get_text(" ", strip=True) if level_text else ""
                # Extract only the integer (e.g., "Lv. 1 [selected]" → 1)
                match = re.search(r"(\d+)", level_raw)
                skill_level = int(match.group(1)) if match else None

                skill_desc = desc_td.get_text(" ", strip=True) if desc_td else ""

                # Absolute link
                base = "/".join(skill_link.split("/")[:3])
                full_link = f"{base}{href}" if href.startswith("/") else href

                print(f"  - Lv. {skill_level}: {full_link}")
                print(f"    → {skill_desc}")

                level_links.append({
                    "level": skill_level,
                    "link": full_link,
                    "description": skill_desc
                })
        else:
            # If no multi-level table, treat current page as single-level
            match = re.search(r"(\d+)", skill_level or "")
            level_int = int(match.group(1)) if match else 1
            level_links = [{
                "level": level_int,
                "link": skill_link,
                "description": skill_description
            }]
            print(f"ℹ️ No multiple levels found for {skill_name} (single level).")

        # --- Loop through all skill levels and scrape their properties ---
        for lvl in level_links:
            # --- HTML cache system ---
            # Create cache directory structure
            os.makedirs(CACHE_DIR, exist_ok=True)
            chronicle_dir = os.path.join(CACHE_DIR, chronicle)
            os.makedirs(chronicle_dir, exist_ok=True)

            # Safe filename for skill
            safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", skill_name.lower()).strip("_")
            cache_path = os.path.join(chronicle_dir, f"{safe_name}_{skill_id}_lv{lvl['level']}.html")

            # --- Load from cache or fetch from web ---
            if os.path.exists(cache_path):
                print(f"📂 Cache found for {skill_name} Lv.{lvl['level']} → {cache_path}")
                with open(cache_path, "r", encoding="utf-8") as f:
                    html_source = f.read()
            else:
                print(f"🌐 Fetching {skill_name} Lv.{lvl['level']} from web...")
                driver.get(lvl["link"])
                time.sleep(WAIT_TIME)
                html_source = driver.page_source
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(html_source)
                print(f"💾 Saved HTML cache → {cache_path}")

            # --- Parse cached or fetched HTML ---
            level_soup = BeautifulSoup(html_source, "html.parser")

            # --- Extract property table ---
            props = {}
            table = level_soup.select_one("table.table-vcenter")
            if table:
                for tr in table.select("tr"):
                    tds = tr.select("td")
                    if len(tds) < 2:
                        continue

                    key_raw = tds[0].get_text(" ", strip=True)
                    val_raw = tds[1].get_text(" ", strip=True)
                    key = to_snake_case(key_raw)
                    val = val_raw.strip()

                    # --- Individual property handling ---
                    if key == "type":
                        val = val.strip()

                    elif key == "uses":
                        # Default
                        mp_cost = None
                        extra_uses = []

                        # --- Extract MP ---
                        mp_match = re.search(r"(\d+)\s*MP", val, re.IGNORECASE)
                        if mp_match:
                            mp_cost = int(mp_match.group(1))

                        # --- Extract extra item uses (like Spirit Ore, Energy Stone, etc.) ---
                        for a in tds[1].select("a.item-name"):
                            item_link = a.get("href", "").strip()
                            # /item/3031/lu4 → 3031
                            item_id_match = re.search(r"/item/(\d+)", item_link)
                            item_id = int(item_id_match.group(1)) if item_id_match else None

                            item_name_tag = a.select_one(".item-name__content")
                            if item_name_tag:
                                item_text = item_name_tag.get_text(" ", strip=True)
                                # "Spirit Ore, 5 pcs" → name + count
                                m = re.match(r"(.+?),\s*(\d+)\s*pcs", item_text)
                                if m:
                                    name = m.group(1).strip()
                                    count = int(m.group(2))
                                else:
                                    name = item_text.strip()
                                    count = None
                            else:
                                name, count = None, None

                            extra_uses.append({
                                "item_id": item_id,
                                "item_name": name,
                                "item_count": count
                            })

                        # Save both MP and extra items
                        val = mp_cost
                        if extra_uses:
                            props["uses_extra"] = json.dumps(extra_uses, ensure_ascii=False)


                    elif key == "cooldown_time":
                        match = re.search(r"(\d+)", val)
                        val = int(match.group(1)) if match else None

                    elif key == "can_it_be_used_at_the_olympiad":
                        val = val.strip().lower() == "yes"

                    elif key == "attribute":
                        val = val.strip()

                    elif key == "trait":
                        val = val.strip("{}").replace("trait_", "").strip()

                    elif key == "range_of_use":
                        match = re.match(r"(\d+)\s*\((\d+)\)", val)
                        if match:
                            props["range_min"] = int(match.group(1))
                            props["range_max"] = int(match.group(2))
                            continue  # skip adding "range_of_use"
                        else:
                            val = val.strip()

                    elif key == "available_for":
                        links = tds[1].select("a")
                        class_data = []
                        for a in links:
                            text = a.get_text(" ", strip=True)
                            m = re.match(r"([A-Za-z\s]+)\s*Lv\.\s*(\d+)", text)
                            if m:
                                cls = m.group(1).strip()
                                lvl_num = int(m.group(2))
                                class_data.append({"class": cls, "level": lvl_num})
                            else:
                                class_data.append({"class": text, "level": None})
                        val = json.dumps(class_data, ensure_ascii=False)

                    else:
                        val = val.strip()

                    props[key] = val

            # --- Clean skill icon filename ---
            icon_clean = re.sub(r"^/icon64/|\.png$", "", icon_src or skill_icon)

            # --- Ensure skill_id is integer ---
            try:
                skill_id_int = int(skill_id)
            except:
                match = re.search(r"(\d+)", str(skill_id))
                skill_id_int = int(match.group(1)) if match else None

            # --- Build data row for this level ---
            data = {
                "skill_id": skill_id_int,
                "skill_name": skill_name,
                "skill_icon": icon_clean,
                "skill_level": lvl["level"],
                "skill_description": lvl["description"],
                "skill_link": lvl["link"],
                "chronicle": chronicle,
            }
            data.update(props)
            results.append(data)
            print(f"✅ Scraped {skill_name} Lv. {lvl['level']}")

        # --- Summary counter ---
        print(f"🏁 Finished {skill_name}: {len(level_links)} levels scraped.")
        print(f"📦 Total records so far: {len(results)}")
    except Exception as e:
        print(f"❌ Error scraping {skill_name}: {e}")
        continue

# --- Save results ---
df_out = pd.DataFrame(results)
df_out.to_csv(OUTPUT_FILE, sep="\t", index=False)
print(f"\n✅ Saved {len(df_out)} skills to {OUTPUT_FILE}")

driver.quit()

# --- GUI viewer ---
try:
    from pandasgui import show
    print("📊 Opening GUI...")
    show(df_out)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")
