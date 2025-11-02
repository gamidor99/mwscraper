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
SERVER_ID = 10
CHRONICLE = "lu4"
INPUT_FILE = "races_classes_lu4.xml"
OUTPUT_FILE = "races_classes_skills_lu4.xml"
LIMIT = 10           # number of class pages to visit (0 = all)
WAIT_TIME = 3     # seconds between pages
LEVEL_FILTER = {"1", "3", "5", "7"}  # which levels to scrape

# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # Uncomment for headless mode
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")

# Optimi
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--blink-settings=imagesEnabled=false")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
options.add_argument("--disable-extensions")
options.add_argument("--disable-background-networking")
options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(15)
wait = WebDriverWait(driver, 15)

# --- SWITCH SERVER FUNCTION ---
def switch_server(driver, wait, server_id, chronicle):
    """Switch MW2 Wiki server and chronicle using CSRF-protected POST requests."""
    print(f"🔄 Switching to server_id={server_id} (chronicle={chronicle})...")
    driver.get(SITE_ROOT)
    time.sleep(2)

    csrf_token = driver.execute_script("""
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : null;
    """)

    if not csrf_token:
        print("❌ CSRF token not found. Make sure you're on the main wiki page.")
        return False

    driver.execute_script("""
        const csrf = arguments[0];
        const serverId = arguments[1];
        const chronicle = arguments[2];
        async function switchSettings() {
            const postData = async (url, body) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRF-Token': csrf
                    },
                    body
                });
                return resp.ok;
            };

            console.log('🛰 Sending POSTs to update server and chronicle...');
            const s1 = await postData('/wiki/profile/set-server', '_csrf=' + encodeURIComponent(csrf) + '&server_id=' + serverId);
            const s2 = await postData('/wiki/profile/set-chronicles', '_csrf=' + encodeURIComponent(csrf) + '&chronicle=' + chronicle);
            console.log('Server POST:', s1, 'Chronicle POST:', s2);

            if (s1 && s2) {
                console.log('✅ Both POSTs succeeded. Reloading...');
                location.reload();
            } else {
                console.error('❌ Failed to switch one or both settings.');
            }
        }
        switchSettings();
    """, csrf_token, server_id, chronicle)

    print("⏳ Waiting for page reload...")
    time.sleep(5)
    try:
        wait.until(lambda d: chronicle.lower() in d.page_source.lower())
        print(f"✅ Switched successfully to server {server_id} ({chronicle}).")
        return True
    except Exception:
        print("⚠️ Switch may not have taken effect.")
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
time.sleep(2)

# --- STEP 2: LOAD XML ---
tree = ET.parse(INPUT_FILE)
root = tree.getroot()

for race_node in root.findall(".//race"):
    for class_node in list(race_node.findall("class")):
        nest_childs(class_node)

# --- STEP 3: COLLECT CLASS LINKS ---
all_classes = []
for class_tag in root.findall(".//class[@url]"):
    all_classes.append((class_tag.attrib["name"], class_tag.attrib["url"], class_tag))

print(f"📚 Found {len(all_classes)} classes total.")
if LIMIT > 0:
    all_classes = all_classes[:LIMIT]
    print(f"🔍 Limiting to first {LIMIT} classes for testing.")

# Ensure chronicle-specific cache folder exists
cache_dir = os.path.join("classes_skills", CHRONICLE)
os.makedirs(cache_dir, exist_ok=True)

# --- STEP 4: SCRAPE LOOP ---
for idx, (class_name, class_url, class_node) in enumerate(all_classes, 1):
    safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', class_name)
    print(f"\n[{idx}/{len(all_classes)}] 🧭 Visiting {class_name} → {class_url}")

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
                print("⚠️ Rate limit detected — sleeping 10 s, then reloading current page...")
                time.sleep(10)
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
            time.sleep(10)
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
                    time.sleep(10)
                    driver.get(level_url)
                    time.sleep(2)
                    level_html = driver.page_source
                    print("🔁 Reloaded after rate limit.")

                with open(level_cache, "w", encoding="utf-8") as f:
                    f.write(level_html)
            except Exception as e:
                print(f"   ⚠️ Could not fetch level {level_num}: {e}")
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
