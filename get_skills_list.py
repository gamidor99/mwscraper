# skills step 1: get skills list from search pages
# --- Config ---
BASE_URL = "https://mw2.wiki"
LIMIT = 1000  # skills per request
MAX_PAGES = 992  # how many pages to scrape
SERVER_ID = 1  # 1=eternal, 2=interlude, 10=lu4black, 11=lu4pink
OUTPUT_FILE = "data/skills/skills_list_eternal.tsv"
WAIT_TIME = 1

START_URL = f"{BASE_URL}/search?query=&type=skill&sub[levelMin]=1&sub[levelMax]=99&sub[race]="
SERVER_NAMES = {
    1: "eternal",
    2: "interlude",
    10: "lu4",
    11: "lu4"
}
CHRONICLE_NAME = SERVER_NAMES.get(SERVER_ID, f"server_{SERVER_ID}").lower()

# --- Setup Selenium ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time, re, os, pandas as pd, csv
from pathlib import Path

options = Options()
# options.add_argument("--headless")
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 15)

# ✅ Collect skills here
all_skills = []

# --- STEP 1: Open skill search page ---
print("🌐 Opening skill search page...")
driver.get(START_URL)
time.sleep(1)

# --- STEP 2: Switch server with CSRF POST ---
csrf_token = driver.execute_script(
    "return document.querySelector('meta[name=\"csrf-token\"]').getAttribute('content');"
)
driver.execute_script(
    """
    fetch('/wiki/profile/set-server', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRF-Token': arguments[0]
        },
        body: '_csrf=' + encodeURIComponent(arguments[0]) + '&server_id=' + arguments[1]
    }).then(() => location.reload());
    """,
    csrf_token,
    SERVER_ID
)
time.sleep(4)
print("✅ Server switched successfully.")

# ✅ Save cookies before restarting browser
cookies = driver.get_cookies()

# 🔄 Restart browser with SPEED mode
driver.quit()
options = Options()
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--blink-settings=imagesEnabled=false")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
options.add_argument("--disable-extensions")
options.add_argument("--disable-background-networking")
options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)
# ✅ 1. Open the base domain first (NOT the search page)
driver.get(BASE_URL)
time.sleep(1)

# ✅ 2. Add cookies now (domain matches)
for cookie in cookies:
    try:
        driver.add_cookie(cookie)
    except Exception as e:
        print(f"⚠️ Skipped cookie {cookie.get('name')}: {e}")

# --- STEP 3: Scrape each page ---
for page in range(1, MAX_PAGES + 1):
    url = f"{BASE_URL}/search?query=&type=skill&sub[levelMin]=1&sub[levelMax]=99&sub[race]=&limit={LIMIT}&page={page}"
    print(f"\n📄 Scraping page {page}/{MAX_PAGES}: {url}")
    driver.get(url)

    print("after this")
    
    # ✅ Get page source
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, "html.parser")
    
    # 🚫 Check for "Empty" row (end of results)
    empty_check = soup.select_one("td.text-center")
    if empty_check and "empty" in empty_check.get_text(strip=True).lower():
        print("⚠️ Empty table detected — stopping pagination.")
        break

    # ✅ Find all skill links
    skill_rows = soup.select("table.table-vcenter a.item-name")

    if not skill_rows:
        print("⚠️ No skills found — stopping.")
        # Optional: print a short snippet to inspect the HTML
        print(page_source[:500])  # show first 500 chars for inspection
        break

    for i, a_tag in enumerate(skill_rows, 1):
        try:
            relative_link = a_tag.get("href", "").strip()
            skill_link = BASE_URL + relative_link

            skill_id_match = re.search(r"/skill/(\d+)-", relative_link)
            skill_id = skill_id_match.group(1) if skill_id_match else ""

            name_tag = a_tag.select_one(".item-name__content")
            skill_name = name_tag.get_text(strip=True) if name_tag else ""

            icon_tag = a_tag.select_one("img")
            skill_icon_full = BASE_URL + icon_tag["src"] if icon_tag and icon_tag.get("src") else ""

            # ✅ Extract icon basename (without .png)
            skill_icon = ""
            if icon_tag and icon_tag.get("src"):
                skill_icon = Path(icon_tag["src"]).stem  # e.g. "skill0001"

            # ✅ Add chronicle info
            chronicle = CHRONICLE_NAME

            all_skills.append({
                "skill_id": skill_id,
                "skill_name": skill_name,
                "skill_icon": skill_icon,          # basename only
                "skill_link": skill_link,
                "chronicle": chronicle             # save chronicle
            })

        except Exception as e:
            print(f"  ❌ Error parsing skill #{i}: {e}")

    print(f"✅ Page {page} done. Total skills collected so far: {len(all_skills)}")

    # 💤 Wait before next page
    if page < MAX_PAGES:
        print(f"⏱️ Waiting {WAIT_TIME}s before next page...")
        time.sleep(WAIT_TIME)


# --- STEP 4: Save TSV ---
df = pd.DataFrame(all_skills)
df.to_csv(OUTPUT_FILE, sep="\t", index=False, quoting=csv.QUOTE_MINIMAL)
print(f"📁 Saved {len(all_skills)} skills to {OUTPUT_FILE}")

# --- STEP 5 Open GUI ---
try:
    from pandasgui import show
    print("📊 Opening GUI...")
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install it with: pip install pandasgui")

# --- Pause before exit ---
#input("\n✅ Scraping complete. Press Enter to exit...")

driver.quit()