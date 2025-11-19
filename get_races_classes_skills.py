# races classes step 3: get skills data from class pages
import os
import time
import re
import xml.etree.ElementTree as ET
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- CONFIG ---
SITE_ROOT = "https://wikipedia1.mw2.wiki"
INPUT_FILE = "data/races_classes/races_details_lu4.xml"
OUTPUT_FILE = "data/races_classes/races_classes_skills_lu4.xml"
LIMIT = 0           # number of class pages to visit (0 = all)
WAIT_TIME = 0.5     # seconds between pages

# --- Chronicle ↔ Server mapping ---
SERVER_ID = 10
CHRONICLE = "lu4"
SERVER_MAP = {
    "eternal": 1,
    "interlude": 2,
    "lu4": 10,
    "lu4_pink": 11
}

SERVER_NAMES = {v: k for k, v in SERVER_MAP.items()}

SERVER_ID = SERVER_MAP.get(CHRONICLE.lower())
if SERVER_ID is None:
    print(f"⚠️ Unknown chronicle '{CHRONICLE}', skipping server switch.")
else:
    CHRONICLE_NAME = SERVER_NAMES.get(SERVER_ID, f"server_{SERVER_ID}").lower()
    print(f"🔄 Switching to server_id={SERVER_ID} ({CHRONICLE_NAME})...")

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # Uncomment for headless mode
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")

# Optimisation
#options.add_argument("--disable-dev-shm-usage")
#options.add_argument("--blink-settings=imagesEnabled=false")
#options.add_argument("--disable-blink-features=AutomationControlled")
#options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
#options.add_argument("--disable-extensions")
#options.add_argument("--disable-background-networking")
#options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(15)
wait = WebDriverWait(driver, 15)

def clean_429_cache(cache_dir):
    print("🧹 Checking cache for 429 HTML files...")

    for root_dir, dirs, files in os.walk(cache_dir):
        for fname in files:
            if not fname.lower().endswith(".html"):
                continue

            path = os.path.join(root_dir, fname)

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                # Detect 429-page in any form
                if (
                    "<title>429 Too Many Requests</title>" in content
                    or "<h1>429 Too Many Requests</h1>" in content
                    or "429 Too Many Requests" in content[:200]  # fast path
                ):
                    print(f"🗑 Removing corrupted 429 cache file: {fname}")
                    os.remove(path)

            except Exception as e:
                print(f"⚠️ Cannot read {fname}: {e}")

    print("✅ Cache cleanup finished.\n")


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





# --- XML HELPERS ---
def reorder_class_nodes(elem):
    """Ensure <skills> comes before <childs> inside each <class>."""
    for cls in elem.findall(".//class"):
        skills = cls.find("skills")
        childs = cls.find("childs")
        if skills is not None and childs is not None:
            cls.remove(skills)
            cls.remove(childs)
            cls.append(skills)
            cls.append(childs)

def nest_childs(parent_elem):
    """Wrap all child <class> elements in <childs> (recursive) and clean empty ones."""
    classes = list(parent_elem.findall("class"))
    if not classes:
        return

    childs_elem = ET.SubElement(parent_elem, "childs")
    for i, c in enumerate(classes):
        parent_elem.remove(c)
        if i == len(classes) - 1:
            c.set("last_child", "true")
        childs_elem.append(c)
        nest_childs(c)

    if len(childs_elem) == 0:
        parent_elem.remove(childs_elem)

# --- STEP 1: SWITCH SERVER ---
switch_server(driver, wait, SERVER_ID, CHRONICLE)
print("✅ Server switch complete.\n")
time.sleep(1)

# --- STEP 2: LOAD XML ---
import xml.etree.ElementTree as ET
import os

# --- STEP 2: LOAD XML ---
tree = ET.parse(INPUT_FILE)
root = tree.getroot()

def nest_childs(node):
    """Recursively ensure nested <class> nodes are linked to their parents (optional)."""
    for child in list(node.findall("class")):
        nest_childs(child)

# --- Flatten nested structure (optional, for traversal correctness) ---
for race_node in root.findall(".//race"):
    for subtype_node in race_node.findall("subtype"):
        for class_node in list(subtype_node.findall("class")):
            nest_childs(class_node)

def parse_all_skills(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    result = {"active": {}, "passive": {}}

    def base_no_ext(url):
        if not url:
            return ""
        return os.path.splitext(os.path.basename(url))[0]

    # Process both tabs
    for tab_name in ["active", "passive"]:
        tab = soup.find("div", id=tab_name)
        if not tab:
            continue

        result_tab = result[tab_name]

        # Each table row inside the tab
        for tr in tab.select("table tbody tr"):
            toggler = tr.find("div", class_="class-simple__toggler")
            if not toggler:
                continue

            category_name = toggler.get_text(strip=True)

            content = tr.find("div", class_="class-simple__content")
            if not content:
                continue

            skills = []

            # All skills inside this category
            for a in content.find_all("a", class_="item-name"):
                href = a.get("href", "").strip()
                full_url = urljoin(SITE_ROOT, href)

                # ID from URL /skill/xxxx-name/1
                m = re.search(r"/skill/(\d+)-", href)
                skill_id = m.group(1) if m else ""

                # Name (from tooltip title)
                title_span = a.select_one(".item-tooltip__title")
                if title_span:
                    name = title_span.get_text(strip=True)
                else:
                    name = a.get_text(strip=True)

                # ICONS (basename without extension)
                icon_primary = ""
                icon_panel = ""

                icon_block = a.select_one("span.item-icon")
                if icon_block:
                    # main icon <img>
                    main_img = icon_block.find("img", class_=None)
                    if main_img:
                        icon_primary = base_no_ext(main_img["src"])

                    # panel icon <img class="item-icon__panel">
                    panel_img = icon_block.find("img", class_="item-icon__panel")
                    if panel_img:
                        icon_panel = base_no_ext(panel_img["src"])

                # DESCRIPTION
                tooltip_text = ""
                tooltip_desc = a.select_one(".item-tooltip > div:nth-of-type(2)")
                if tooltip_desc:
                    tooltip_text = tooltip_desc.get_text(" ", strip=True)

                skills.append({
                    "id": skill_id,
                    "name": name,
                    "level": "1",
                    "url": full_url,
                    "icon": icon_primary,       # no extension
                    "icon_panel": icon_panel,   # no extension
                    "description": tooltip_text
                })

            result_tab[category_name] = skills

    return result






def write_skills_summary_to_xml(class_node, summary_data):
    """
    Writes <skills_summary> in this structure:

    <skills_summary>
        <skills type="active">
            <category name="Physical skills">
                <skill .../>
            </category>
        </skills>

        <skills type="passive">
            <category name="Equipment skills">
                <skill .../>
            </category>
        </skills>
    </skills_summary>
    """

    # Remove old summary
    old = class_node.find("skills_summary")
    if old is not None:
        class_node.remove(old)

    root_summary = ET.SubElement(class_node, "skills_summary")

    for tab_name, categories in summary_data.items():
        # <skills type="active"> or <skills type="passive">
        skills_node = ET.SubElement(root_summary, "skills", type=tab_name)

        for category_name, skills in categories.items():
            # <category name="Physical skills">
            cat_node = ET.SubElement(skills_node, "category", name=category_name)

            for sk in skills:
                ET.SubElement(
                    cat_node,
                    "skill",
                    id=sk["id"],
                    name=sk["name"],
                    level=sk["level"],
                    icon=sk["icon"],          # no extension
                    icon_panel=sk["icon_panel"],
                    url=sk["url"]
                )



# --- STEP 3: COLLECT CLASS LINKS ---
all_classes = []
for class_tag in root.findall(".//class[@link]"):
    name = class_tag.attrib.get("name", "")
    url = class_tag.attrib.get("link", "")
    if url:
        all_classes.append((name, url, class_tag))

print(f"📚 Found {len(all_classes)} classes total.")

if LIMIT > 0:
    all_classes = all_classes[:LIMIT]
    print(f"🔍 Limiting to first {LIMIT} classes for testing.")

# Ensure chronicle-specific cache folder exists
cache_dir = os.path.join("cache/classes_skills", CHRONICLE)
os.makedirs(cache_dir, exist_ok=True)

# Clean any cached 429 files before starting
clean_429_cache(cache_dir)

print(all_classes)

# --- STEP 4: SCRAPE LOOP (skeleton) ---
for idx, (class_name, class_url, class_node) in enumerate(all_classes, 1):
    print(f"[{idx}/{len(all_classes)}] 🌐 {class_name} → {class_url}")
    # (fetch, cache, parse, etc.)

    safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', class_name)

    # --- Load from cache if available ---
    cached_path = os.path.join(cache_dir, f"class_{safe_name}.html")
    if os.path.exists(cached_path):
        print(f"📦 Using cached HTML for {class_name} ({os.path.basename(cached_path)})")
        with open(cached_path, "r", encoding="utf-8") as f:
            page_html = f.read()

        # Visit the live page anyway to ensure correct server context
        try:
            driver.get(class_url)
            time.sleep(1.5)
        except Exception as e:
            print(f"⚠️ Could not reload browser context for {class_name}: {e}")

        # If cache looks incomplete, refetch from live site
        if len(page_html) < 5000 or "By levels" not in page_html:
            print(f"⚠️ Cached file {os.path.basename(cached_path)} seems incomplete — reloading from live site.")
            from selenium.common.exceptions import TimeoutException

        try:
            driver.set_page_load_timeout(30)
            driver.get(class_url)
            time.sleep(WAIT_TIME)
            page_html = driver.page_source

            # --- Handle rate limiting (429) ---
            if "429 Too Many Requests" in page_html:
                print("⚠️ Rate limit detected — sleeping, then reloading current page...")
                time.sleep(WAIT_TIME *2)
                try:
                    driver.get(class_url)
                    time.sleep(2)
                    page_html = driver.page_source
                    print("🔁 Reloaded current page after rate limit.")
                except Exception as e:
                    print(f"❌ Reload failed after 429: {e}")
                    continue

            # --- Save to cache ---
            with open(cached_path, "w", encoding="utf-8") as f:
                f.write(page_html)

        except TimeoutException:
            # Page likely loaded but Selenium timed out waiting for 'complete'
            print(f"⚠️ Timeout while loading {class_name}, but page may be loaded — continuing.")
            page_html = driver.page_source
            with open(cached_path, "w", encoding="utf-8") as f:
                f.write(page_html)

        except Exception as e:
            print(f"❌ Failed to load {class_name}: {e}")

            # Try to recover from cache if available
            if os.path.exists(cached_path):
                print(f"📦 Using cached HTML for {class_name} ({os.path.basename(cached_path)})")
                with open(cached_path, "r", encoding="utf-8") as f:
                    page_html = f.read()
            else:
                print("🚫 No cached file available — skipping this class.")
                continue

    else:
        # no cache, load live
        print(f"🌐 No cached HTML for {class_name}, loading live page.")
        driver.get(class_url)
        time.sleep(WAIT_TIME)
        page_html = driver.page_source

        # --- Handle rate limiting (429) ---
        if "429 Too Many Requests" in page_html:
            print("⚠️ Rate limit detected — sleeping 10 s, then reloading current page...")
            time.sleep(WAIT_TIME*2)
            try:
                driver.get(class_url)
                time.sleep(2)
                page_html = driver.page_source
                print("🔁 Reloaded current page after rate limit.")
            except Exception as e:
                print(f"❌ Reload failed after 429: {e}")
                continue



        with open(cached_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        

    # --- Check for 404 ---
    if "404" in page_html.lower() and ("not found" in page_html.lower() or "page not found" in page_html.lower()):
        print(f"⚠️ 404 detected for {class_name} — removing from XML.")
        for p in root.iter():
            if class_node in list(p):
                p.remove(class_node)
                break
        continue

    # --- Click "By levels" tab ---
    soup = BeautifulSoup(page_html, "html.parser")
    try:
        by_levels_tab = driver.find_element(By.XPATH, "//a[contains(text(), 'By levels')]")
        driver.execute_script("arguments[0].click();", by_levels_tab)
        time.sleep(1)
    except Exception:
        print("⚠️ 'By levels' tab not found — continuing anyway.")

    soup = BeautifulSoup(driver.page_source, "html.parser")
    level_links = soup.select("a.skill-level-link")
    print(f"🔍 Found {len(level_links)} level links.")

    if not level_links:
        print("❌ No level links found.")
        continue

    # Remove any old <skills> node before starting
    old_skills = class_node.find("skills")
    if old_skills is not None:
        class_node.remove(old_skills)

    skills_node = ET.SubElement(class_node, "skills")
    levels_added = 0  # track how many levels were actually found

    for level_link in level_links:
        level_num = level_link.get_text(strip=True)
        if not level_num.isdigit():
            continue

        level_url = urljoin(SITE_ROOT, level_link.get("href", ""))
        print(f"   🧩 Fetching level {level_num} → {level_url}")

        # Load cached or fresh HTML (same logic you have now)
        level_cache = os.path.join(cache_dir, f"class_{safe_name}_level_{level_num}.html")
        if os.path.exists(level_cache):
            with open(level_cache, "r", encoding="utf-8") as f:
                level_html = f.read()
        else:
            try:
                link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[contains(@class,'skill-level-link') and normalize-space(text())='{level_num}']"))
                )
                driver.execute_script("arguments[0].click();", link)
                time.sleep(1.5)
                level_html = driver.page_source

                if "429 Too Many Requests" in level_html:
                    print("⚠️ Rate limit detected — sleeping 10s then reloading...")
                    time.sleep(WAIT_TIME*2)
                    driver.get(level_url)
                    #time.sleep(2)
                    level_html = driver.page_source
                    print("🔁 Reloaded after rate limit.")

                with open(level_cache, "w", encoding="utf-8") as f:
                    f.write(level_html)
            except Exception as e:
                print(f"   ⚠️ Could not fetch level {level_num}: {e}")
                try:
                    print("   🔁 Trying to refresh the page and re-fetch level HTML...")
                    driver.refresh()
                    time.sleep(1.5)
                    level_html = driver.page_source

                    # Handle rate limiting after refresh
                    if "429 Too Many Requests" in level_html:
                        print("   ⚠️ Rate limit detected after refresh — sleeping then navigating to level URL...")
                        time.sleep(WAIT_TIME*2)
                        try:
                            driver.get(level_url)
                            time.sleep(1.5)
                            level_html = driver.page_source
                        except Exception as e2:
                            print(f"   ❌ Failed to load level URL after 429: {e2}")
                            raise

                    # Save refreshed HTML to cache
                    with open(level_cache, "w", encoding="utf-8") as f:
                        f.write(level_html)

                except Exception as e2:
                    print(f"   ❌ Refresh/reload failed for level {level_num}: {e2}")
                    # Fallback to existing cache if available
                    if os.path.exists(level_cache):
                        print(f"   📦 Falling back to cached level HTML: {os.path.basename(level_cache)}")
                        with open(level_cache, "r", encoding="utf-8") as f:
                            level_html = f.read()
                    else:
                        print("   🚫 No cached level file available — skipping this level.")
                        continue

        soup = BeautifulSoup(level_html, "html.parser")
        table = soup.find("table", class_="table-skills")
        if not table:
            continue

        level_node = ET.SubElement(skills_node, "level", number=level_num)
        tbody = table.find("tbody")
        if not tbody:
            continue

        skills_found = 0
        for tr in tbody.find_all("tr"):
            skill_a = tr.find("a", class_="item-name")
            if not skill_a:
                continue

            skill_name_full = skill_a.find("span", class_="item-name__content").get_text(strip=True)
            skill_href = urljoin(SITE_ROOT, skill_a.get("href", ""))
            skill_icon_tag = skill_a.find("img")
            skill_icon = urljoin(SITE_ROOT, skill_icon_tag["src"]) if skill_icon_tag else ""

            icon_name = os.path.splitext(os.path.basename(skill_icon_tag["src"]))[0] if skill_icon_tag else ""
            skill_id_match = re.search(r"/skill/(\d+)-", skill_href)
            skill_id = skill_id_match.group(1) if skill_id_match else ""

            note_td = tr.find("td", class_="text-end")
            note_text = note_td.get_text(strip=True) if note_td else ""

            skill_level = "1"
            if "Lv." in skill_name_full:
                parts = skill_name_full.split("Lv.")
                skill_name = parts[0].strip()
                skill_level = parts[1].strip(" .")
            else:
                skill_name = skill_name_full

            ET.SubElement(
                level_node,
                "skill",
                id=skill_id,
                name=skill_name,
                level=skill_level,
                icon_name=icon_name,
                url=skill_href,
                icon=skill_icon,
                note=note_text
            )
            skills_found += 1

        if skills_found > 0:
            print(f"   ✅ {skills_found} skills collected at level {level_num}")
            levels_added += 1
        else:
            # Remove empty <level> if nothing inside
            skills_node.remove(level_node)

    

    # If no levels added at all, remove empty <skills>
    if levels_added == 0:
        class_node.remove(skills_node)
        print(f"⚠️ No skills found for {class_name}, skipping <skills> section.")
    else:
        print(f"✅ Added {levels_added} levels to {class_name}")

    # test: remove all skills (for debugging)
    #class_node.remove(skills_node)









    # --------------------------------------------------------
    # ALL SKILLS SUMMARY — CACHE SYSTEM
    # --------------------------------------------------------
    summary_cache_path = os.path.join(cache_dir, f"class_{safe_name}_summary.html")

    if os.path.exists(summary_cache_path):
        # ✔ Load from cache, no clicking
        print(f"📦 Using cached ALL SKILLS for {class_name}")
        with open(summary_cache_path, "r", encoding="utf-8") as f:
            page_html = f.read()

    else:
        # ❌ Cache does not exist → must click and fetch
        print(f"🌐 Loading ALL SKILLS tab for {class_name}...")

        # --- Click "All skills" tab to reset ---
        try:
            all_skills_link = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@class,'nav-link') and contains(text(),'All skills')]")
                )
            )
            all_skills_link.click()
        except Exception as e:
            print(f"⚠️ Cannot click All skills tab: {e}")

        time.sleep(1)
        page_html = driver.page_source

        # Handle rate limit
        if "429 Too Many Requests" in page_html:
            print("⚠️ 429 detected — waiting 10s...")
            time.sleep(WAIT_TIME * 2)
            page_html = driver.page_source

        # ✔ Save fresh cache
        with open(summary_cache_path, "w", encoding="utf-8") as f:
            f.write(page_html)


    # --------------------------------------------------------
    # PARSE + WRITE TO XML
    # --------------------------------------------------------
    summary_data = parse_all_skills(page_html)
    write_skills_summary_to_xml(class_node, summary_data)




    

    


driver.quit()

# --- STEP 5: CLEANUP ---
print("\n🧹 Finalizing XML structure...")

for race_node in root.findall(".//race"):
    for class_node in list(race_node.findall("class")):
        nest_childs(class_node)

reorder_class_nodes(root)

# Remove empty <childs> safely
print("🧹 Removing empty <childs> nodes...")
for empty_childs in list(root.findall(".//childs")):
    if len(empty_childs) == 0:
        for p in root.iter():
            if empty_childs in list(p):
                p.remove(empty_childs)
                break

# --- STEP 6: SAVE OUTPUT ---
ET.indent(root, space="  ")
ET.ElementTree(root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
abs_path = os.path.abspath(OUTPUT_FILE)
print(f"\n✅ XML with <childs> and <skills> saved to: {abs_path}")
