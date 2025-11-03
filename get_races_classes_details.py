# races classes step 2: get details with stats
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
import xml.etree.ElementTree as ET
from collections import defaultdict

# --- Config ---
INPUT_FILE = "data/races_classes/races_eternal.tsv"

OUTPUT_FILE = "data/races_classes/races_details_eternal.tsv"
OUTPUT_XML = "data/races_classes/races_details_eternal.xml"

CACHE_DIR = "cache/classes_details"
BASE_URL = "https://wikipedia1.mw2.wiki"
WAIT_TIME = 3
LIMIT = 12

# --- Chronicle ↔ Server mapping ---
SERVER_ID = 1
CHRONICLE = "eternal"
SERVER_MAP = {
    "eternal": 1,
    "interlude": 2,
    "lu4": 10,
    "lu4_pink": 11
}

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

def extract_bg_url(style: str) -> str:
    """Extract a URL from a background-image CSS style."""
    if not style:
        return ""
    match = re.search(r'url\((["\']?)(.*?)\1\)', style)
    if match:
        url = match.group(2)
        if url.startswith("/"):
            return BASE_URL + url
        return url
    return ""

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

def indent_with_tabs(elem: ET.Element, level: int = 0):
    """Pretty-print XML with tabs instead of spaces."""
    i = "\n" + ("\t" * level)
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        for idx, e in enumerate(elem):
            indent_with_tabs(e, level + 1)
            if not e.tail or not e.tail.strip():
                e.tail = i + ("\t" if idx < len(elem) - 1 else "")
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def parse_class_li(li_tag, parent_elem):
    """Recursively parse <li> into XML <class> elements."""
    a_tag = li_tag.find("a")
    if not a_tag:
        return

    name = a_tag.get_text(strip=True)
    href = a_tag.get("href")
    link = BASE_URL + href if href and href.startswith("/") else href
    is_final = "no-child" in (a_tag.get("class") or [])

    class_elem = ET.SubElement(parent_elem, "class", {"name": name, "link": link or ""})
    if is_final:
        return

    # Find nested <ul> of next tier
    next_ul = li_tag.find("ul", class_="race-class__ul")
    if next_ul:
        for child_li in next_ul.find_all("li", recursive=False):
            parse_class_li(child_li, class_elem)

def parse_race_section(li_tag, parent_elem):
    """Parse a <li> containing a race (Human, Elf, etc.) into XML."""
    img_tag = li_tag.find("img")
    race_icon = ""
    if img_tag and img_tag.get("src"):
        race_icon = clean_url(BASE_URL + img_tag["src"]) if img_tag["src"].startswith("/") else img_tag["src"]

    # ✅ Try to extract text immediately after the <img>
    race_name = "Unknown"
    if img_tag and img_tag.next_sibling:
        text = img_tag.next_sibling.strip()
        if text:
            race_name = text
        else:
            # Fallback: look for direct text nodes that aren't nested
            direct_texts = [t for t in li_tag.find_all(string=True, recursive=False) if t.strip()]
            if direct_texts:
                race_name = direct_texts[0].strip()

    race_elem = ET.SubElement(parent_elem, "race", {"name": race_name, "icon": race_icon})

    first_ul = li_tag.find("ul", class_="race-class__first-ul")
    if not first_ul:
        return

    for subtype_li in first_ul.find_all("li", recursive=False):
        subtype_a = subtype_li.find("a")
        subtype_name = subtype_a.get_text(strip=True) if subtype_a else "Unknown"
        subtype_link = BASE_URL + subtype_a["href"] if subtype_a and subtype_a.get("href", "").startswith("/") else ""
        subtype_elem = ET.SubElement(race_elem, "subtype", {"name": subtype_name, "link": subtype_link})

        next_ul = subtype_li.find("ul", class_="race-class__ul")
        if next_ul:
            for class_li in next_ul.find_all("li", recursive=False):
                parse_class_li(class_li, subtype_elem)




def switch_server(driver, wait, server_id, chronicle):
    """Switch MW2 Wiki server using visible dropdown menu (robust version)."""
    SITE_ROOT = "https://wikipedia1.mw2.wiki"

    print(f"🔄 Switching to server_id={server_id} (chronicle={chronicle})...")
    driver.get(SITE_ROOT)
    time.sleep(2)

    try:
        # --- Wait for dropdown toggle ---
        dropdown_toggle = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a#dropdown-server"))
        )

        # --- Ensure it's visible on screen ---
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_toggle)
        time.sleep(0.5)

        # --- Try to click using JS (avoids not interactable errors) ---
        driver.execute_script("arguments[0].click();", dropdown_toggle)
        time.sleep(1)

        # --- Wait for dropdown menu to render ---
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".dropdown-menu.show")))

        # --- Find matching option ---
        items = driver.find_elements(By.CSS_SELECTOR, ".dropdown-menu a.dropdown-item")
        found = False
        for item in items:
            data_params = item.get_attribute("data-params") or ""
            if f'"server_id":{server_id}' in data_params:
                label = item.text.strip()
                print(f"🖱 Clicking server option: {label}")
                driver.execute_script("arguments[0].click();", item)
                found = True
                break

        if not found:
            print(f"❌ Server ID {server_id} not found in dropdown menu.")
            return False

        # --- Wait for reload ---
        print("⏳ Waiting for page reload...")
        time.sleep(5)
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")

        # --- Confirm dropdown text ---
        new_label = driver.find_element(By.CSS_SELECTOR, "a#dropdown-server").text.strip()
        print(f"✅ Active server now: {new_label}")
        if chronicle.lower() in new_label.lower() or str(server_id) in new_label:
            print(f"✅ Switched successfully to {new_label}.")
            return True
        else:
            print(f"⚠️ Switch may not have taken effect → Dropdown shows: {new_label}")
            return False

    except Exception as e:
        print(f"⚠️ Error switching to server {server_id} ({chronicle}): {e}")
        return False





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

# --- STEP 1: SWITCH SERVER ---
switch_server(driver, wait, SERVER_ID, CHRONICLE)
print("✅ Server switch complete.\n")
time.sleep(1)

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







# --- Parse HTML ---
print("🔍 Parsing race/class hierarchy...")
soup = BeautifulSoup(html_source, "html.parser")
tree_root = soup.select_one("div#race-class__list")
if not tree_root:
    raise SystemExit("❌ Could not find <div id='race-class__list'>")

root_elem = ET.Element("classes")
ul_root = tree_root.find("ul")
race_items = ul_root.find_all("li", recursive=False)
if LIMIT:
    race_items = race_items[:LIMIT]

for race_li in race_items:
    parse_race_section(race_li, root_elem)

# --- Save XML ---
indent_with_tabs(root_elem)
ET.ElementTree(root_elem).write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)
print(f"✅ Saved XML → {OUTPUT_XML}")

# --- Optional preview ---
print("📁 Example structure:")
for race in root_elem.findall("race"):
    print("─", race.get("name"))
    for st in race.findall("subtype"):
        print("   ├─", st.get("name"))











# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(df_out)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

driver.quit()
print("🏁 Done.")
