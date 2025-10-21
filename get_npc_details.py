import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import csv

# --- CONFIG ---
BASE_SITE = "https://wiki.mw2.wiki"
INPUT_FILE = "npc_list.csv"
OUTPUT_FILE = "npc_details.tsv"
CHECKPOINT_FILE = "npc_details_checkpoint.tsv"
SLEEP_BETWEEN = 0.5
CHRONICLE = "lu4"  # lu4 or "interlude", etc.

OFFSET = 0      # skip first N rows before scraping
MAX_NPCS = 999100  # 0 = all, or limit for testing

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # optional
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

# for speed
options.add_argument("--blink-settings=imagesEnabled=false")  # disable images (faster)
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
options.add_argument("--disable-extensions")
options.add_argument("--disable-background-networking")
options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(15)

# --- Helpers ---
def to_snake_case(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")

def normalize_value(val: str):
    val = val.strip().replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", val.replace("%", "")):
        return float(val.replace("%", "")) if "." in val else int(val.replace("%", ""))
    return val

def parse_defence_attributes(td_content: str):
    elements = re.findall(r"([A-Za-z]+)[^\d]*(\d+)", td_content)
    return {to_snake_case(f"def_{el}"): int(val) for el, val in elements}

# --- Drop & Spoil Parser ---
def parse_drop_table(table):
    drops = []
    group_chance = None
    rows = table.select("tbody tr")

    for tr in rows:
        # detect group chance rows
        if "Group chance" in tr.get_text():
            m = re.search(r"Group chance:\s*([\d\.]+)%", tr.get_text())
            group_chance = float(m.group(1)) if m else None
            continue

        a_tag = tr.select_one("a.item-name")
        if not a_tag:
            continue

        name_tag = a_tag.select_one(".item-name__content")
        item_grade_tag = a_tag.select_one(".item-grade")

        name_tag = a_tag.select_one(".item-name__content")
        item_grade = item_grade_tag.get_text(strip=True) if item_grade_tag else ""

        # ✅ Get item name only from the main text node (excluding nested spans)
        if name_tag:
            # Extract only the text directly inside .item-name__content (not child spans)
            item_name = "".join(t for t in name_tag.find_all(string=True, recursive=False)).strip()
        else:
            item_name = ""

        # ✅ Remove grade text if still present (just in case)
        if item_grade_tag:
            grade_text = item_grade_tag.get_text(strip=True)
            item_name = re.sub(rf"\b{re.escape(grade_text)}\b", "", item_name).strip()

        if item_grade_tag:
            grade_text = item_grade_tag.get_text(strip=True)
            item_name = re.sub(rf"\b{re.escape(grade_text)}\b", "", item_name).strip()

       

        # ✅ Other fields
        href = urljoin(BASE_SITE, a_tag.get("href", ""))
        icon_tag = a_tag.select_one("img")
        icon_url = urljoin(BASE_SITE, icon_tag["src"]) if icon_tag else ""

        # ✅ Extract numeric ID from the URL (e.g. /item/8604-...)
        m = re.search(r"/item/(\d+)", href)
        item_id = m.group(1) if m else None

        # ✅ Normalize icon filename (e.g. etc_magic_sp_herb_i00)
        icon_filename = None
        if icon_url:
            m_icon = re.search(r"/([^/]+)\.png", icon_url)
            if m_icon:
                icon_filename = m_icon.group(1)

        amount = normalize_value(tr.select_one("td.text-center").get_text(strip=True))
        chance = normalize_value(tr.select_one("td.text-end").get_text(strip=True))

        drops.append({
            "id": item_id,                      # ← numeric ID or NONE
            "name": item_name,
            "grade": item_grade,
            "url": href,
            "icon": icon_filename,             # ← cleaned icon name
            "amount": amount,
            "chance_percent": chance,
            "group_chance_percent": group_chance
        })

    return drops

# --- Skill parser ---
def parse_skills_table(table):
    skills = []

    for tr in table.select("tbody tr"):
        a_tag = tr.select_one("a.item-name")
        if not a_tag:
            continue

        # ✅ Skill name (safe extraction, preserving original case)
        name_tag = a_tag.select_one(".item-name__content")
        if name_tag:
            # Only direct text (ignore nested spans)
            skill_name = "".join(t for t in name_tag.find_all(string=True, recursive=False)).strip()
        else:
            # fallback: try text from link itself
            skill_name = a_tag.get_text(strip=True)

        # ✅ Skill URL
        skill_url = urljoin(BASE_SITE, a_tag.get("href", ""))

        # ✅ Skill ID from URL
        m = re.search(r"/skill/(\d+)", skill_url)
        skill_id = m.group(1) if m else None

        # ✅ Skill icon (filename only)
        icon_tag = a_tag.select_one("img")
        skill_icon_url = urljoin(BASE_SITE, icon_tag["src"]) if icon_tag else ""
        if skill_icon_url:
            m_icon = re.search(r"/([^/]+)\.png", skill_icon_url)
            skill_icon = m_icon.group(1) if m_icon else None
        else:
            skill_icon = None

        skills.append({
            "id": skill_id,
            "name": skill_name,
            "url": skill_url,
            "icon": skill_icon
        })

    return skills


# --- Spawn parser ---
def parse_spawn_points(soup):
    points = []
    map_img_tag = soup.select_one("#map img#bg")
    map_img = urljoin(BASE_SITE, map_img_tag["src"]) if map_img_tag else ""
    for span in soup.select("#map .spawn-point"):
        top = float(span.get("style").split("top:")[1].split("px")[0])
        left = float(span.get("style").split("left:")[1].split("px")[0])
        points.append({"top": top, "left": left})
    return map_img, points

# --- Load CSV ---
df = pd.read_csv(INPUT_FILE)

# --- Delete checkpoint file --
if os.path.exists(CHECKPOINT_FILE):
    os.remove(CHECKPOINT_FILE)
    print(f"🗑️ Deleted existing checkpoint file: {CHECKPOINT_FILE}")

if OFFSET > 0:
    df = df.iloc[OFFSET:]   # ✅ skip first OFFSET rows
    print(f"⏩ Skipping first {OFFSET} NPCs")

if MAX_NPCS > 0:
    df = df.head(MAX_NPCS)
    print(f"⚙️ Limiting scraping to first {MAX_NPCS} NPCs")

results = []

# --- Visit each NPC page ---
for idx, row in df.iterrows():
    name = row["name"]
    url = row["url"]

    # ✅ Extract npc_id and chronicle BEFORE visiting
    m = re.search(r"/npc/(\d+)-[^/]+/([^/]+)/?$", url)
    npc_id = int(m.group(1)) if m else None
    chronicle = m.group(2) if m else None
    print(f"🔎 [{idx+1}/{len(df)}] Preparing: {name} (ID: {npc_id}, Chronicle: {chronicle})")

    url = re.sub(r"/npc/(\d+-[^/]+)/[^/]+/?$", rf"/npc/\1/{CHRONICLE}", url)

    try:
        driver.get(url)
    except Exception:
        print(f"⚠️ Timeout loading {url}")

    time.sleep(SLEEP_BETWEEN)

    soup = None
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 🏷️ Title + icon
        title_div = soup.select_one("#result-title")
        title = title_div.get_text(strip=True) if title_div else name
        icon_url = ""
        if title_div:
            img_tag = title_div.select_one("img")
            if img_tag and img_tag.get("src"):
                icon_url = urljoin(BASE_SITE, img_tag["src"])

        # 📊 Stats
        stats = {}
        stats_table = soup.select_one("#result-stats table")
        if stats_table:
            for tr in stats_table.select("tr"):
                tds = tr.find_all("td")
                for i in range(0, len(tds), 2):
                    if i + 1 < len(tds):
                        key = to_snake_case(tds[i].get_text(strip=True))
                        val = normalize_value(tds[i + 1].get_text(strip=True))
                        stats[key] = val

        defence_raw = stats.get("defence_attribute")
        if defence_raw:
            stats.update(parse_defence_attributes(defence_raw))

        # 💰 Drop / Spoil
        drops = parse_drop_table(soup.select_one("#drop table")) if soup.select_one("#drop table") else []
        spoils = parse_drop_table(soup.select_one("#spoil table")) if soup.select_one("#spoil table") else []

        # 📚 Skills
        skills = parse_skills_table(soup.select_one("#skills table")) if soup.select_one("#skills table") else []

        # 📍 Spawn points
        map_img, spawn_points = parse_spawn_points(soup)

        npc_info = {
            "npc_id": npc_id,
            "chronicle": CHRONICLE,   # ✅ use new chronicle,
            "name": name,
            "url": url,
            "title": title,
            "icon_url": icon_url,
            **stats,
            "drops": drops,
            "spoils": spoils,
            "skills": skills,
            "map_image": map_img,
            "spawn_points": spawn_points
        }

        results.append(npc_info)

    except Exception as e:
        print(f"⚠️ Error parsing {name}: {e}")

    if soup is None:
        print(f"⚠️ Failed to load HTML for {name} — skipping.")
        continue

    if idx % 50 == 0 and idx > 0:
        pd.DataFrame(results).to_csv(
            CHECKPOINT_FILE,
            sep="\t",          
            index=False,
            quoting=csv.QUOTE_NONE,
            encoding="utf-8"
        )

        print(f"💾 Checkpoint saved at NPC #{idx}")


# --- Convert nested lists to JSON strings ---
for npc in results:
    for field in ["drops", "spoils", "skills", "spawn_points"]:
        if field in npc:
            npc[field] = json.dumps(npc[field], ensure_ascii=False)

# --- Save to TSV ---
details_df = pd.DataFrame(results)
details_df.columns = [to_snake_case(c) for c in details_df.columns]

# --- Clean nested JSON fields ---
for npc in results:
    for field in ["drops", "spoils", "skills", "spawn_points"]:
        if field in npc and isinstance(npc[field], list):
            # strip whitespace/tabs inside nested objects too
            for item in npc[field]:
                for k, v in item.items():
                    if isinstance(v, str):
                        item[k] = v.strip().replace("\t", " ")
            npc[field] = json.dumps(npc[field], ensure_ascii=False)

# --- Create DataFrame ---
details_df = pd.DataFrame(results)

# --- Normalize all string columns ---
for col in details_df.columns:
    if details_df[col].dtype == "object":
        details_df[col] = details_df[col].astype(str).str.strip().str.replace("\t", " ", regex=False)

# --- Save to TSV ---
#details_df.to_csv(OUTPUT_FILE, sep="\t", index=False, quoting=1, encoding="utf-8")
#details_df.to_csv(OUTPUT_FILE,sep="\t", index=False, quoting=csv.QUOTE_ALL, escapechar="\\", doublequote=True, encoding="utf-8")
details_df.to_csv(
    OUTPUT_FILE,
    sep="\t",           # ✅ only tabs as separator
    index=False,
    quoting=csv.QUOTE_NONE,
    encoding="utf-8"
)

print(f"✅ Done! Saved {len(details_df)} NPC details to {OUTPUT_FILE} with JSON-encoded nested fields.")

# --- GUI (optional) ---
try:
    from pandasgui import show
    show(details_df.copy())  # ✅ safer to use .copy()
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")
    print(details_df.head())
except Exception as e:
    print(f"⚠️ GUI failed to open: {e}")
    print(details_df.head())



# --- Exit ---
input("🔚 Press Enter to exit...")

driver.quit()