# --- Config ---
BASE_URL = "https://mw2.wiki"
LIMIT = 1000  # items per request
MAX_PAGES = 999  # how many pages to scrape
SERVER_ID = 10  # 1=eternal, 2=interlude, 10=lu4black, 11=lu4pink
OUTPUT_FILE = "items_list.tsv"
WAIT_TIME = 2  # wait time (seconds) between pages

START_URL = f"{BASE_URL}/search?query=&type=item&sub[levelMin]=1&sub[levelMax]=99&sub[race]=&limit={LIMIT}&page=1"
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
import time, re, pandas as pd, csv, sys

options = Options()
# options.add_argument("--headless")
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 15)

# ✅ Collect items here
all_items = []

# --- STEP 1: Open item search page ---
print("🌐 Opening item search page...")
driver.get(START_URL)
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
time.sleep(1)

# --- STEP 2: Switch server with CSRF POST ---
print("🔄 Switching server...")
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

# --- STEP 3: Restart browser in speed mode ---
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
driver.get(START_URL)

# ✅ Restore session cookies
for cookie in cookies:
    driver.add_cookie(cookie)

driver.get(START_URL)
time.sleep(2)
print("⚡ Speed-optimized scraping session started.")

# --- STEP 4: Scrape pages ---
for page in range(1, MAX_PAGES + 1):
    url = f"{BASE_URL}/search?query=&type=item&sub[levelMin]=1&sub[levelMax]=99&sub[race]=&limit={LIMIT}&page={page}"
    print(f"📄 Scraping page {page}/{MAX_PAGES}: {url}")
    driver.get(url)
    
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # 🧩 Check for "Empty" row
    empty_row = soup.select_one("table.table tbody tr td.text-center")
    if empty_row and "Empty" in empty_row.get_text(strip=True):
        print("⚠️ Empty page detected — stopping scraper.")
        break

    rows = soup.select("table.table tbody tr")
    if not rows:
        print("⚠️ No rows found — stopping.")
        break

    for row in rows:
        a_tag = row.select_one("a.item-name")
        if not a_tag:
            continue
        
        relative_link = a_tag.get("href", "").strip()
        item_link = BASE_URL + relative_link

        # Extract ID
        item_id_match = re.search(r"/item/(\d+)-", relative_link)
        item_id = item_id_match.group(1) if item_id_match else ""

        # Extract name (without grade)
        name_tag = a_tag.select_one(".item-name__content")
        grade_tag = a_tag.select_one(".item-grade")

        # Temporarily remove grade text from name
        if name_tag:
            item_name = name_tag.get_text(strip=True)
            if grade_tag:
                grade_text = grade_tag.get_text(strip=True)
                # Remove grade text from the end of the name if present
                if item_name.endswith(grade_text):
                    item_name = item_name[: -len(grade_text)].strip()
        else:
            item_name = ""

        # Extract grade
        item_grade = grade_tag.get_text(strip=True) if grade_tag else ""


        # Extract icon filename only
        icon_tag = a_tag.select_one("img")
        icon_src = icon_tag.get("src") if icon_tag and icon_tag.get("src") else ""
        icon_filename = icon_src.split("/")[-1].replace(".png", "") if icon_src else ""

        # Extract grade
        grade_tag = a_tag.select_one(".item-grade")
        item_grade = grade_tag.get_text(strip=True) if grade_tag else ""

        all_items.append({
            "id": item_id,
            "name": item_name,
            "icon": icon_filename,
            "grade": item_grade,
            "link": item_link,
            "chronicle": CHRONICLE_NAME
        })

    print(f"✅ Page {page} done. Total items collected: {len(all_items)}")

    if page < MAX_PAGES:
        print(f"⏱️ Waiting {WAIT_TIME}s before next page...")
        time.sleep(WAIT_TIME)

# --- STEP 5: Save TSV ---
if not all_items:
    print("⚠️ No items collected. Exiting.")
    driver.quit()
    sys.exit()

df = pd.DataFrame(all_items, columns=["id", "name", "icon", "grade", "link", "chronicle"])
df.to_csv(OUTPUT_FILE, sep="\t", index=False, quoting=csv.QUOTE_MINIMAL)
print(f"\n💾 Saved {len(df)} items to {OUTPUT_FILE}")

# --- STEP 6: Optional GUI view ---
try:
    from pandasgui import show
    print("📊 Opening GUI...")
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install it with: pip install pandasgui")

# --- STEP 7: Pause before exit ---
input("\n✅ Scraping complete. Press Enter to exit...")

driver.quit()
