# races classes step 1: get list
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import argparse

# --- Config ---
BASE_URL = "https://wikipedia1.mw2.wiki"
INPUT_URL = f"{BASE_URL}/races"
OUTPUT_FILE = "data/races_classes/races_eternal.tsv"

# Default server and chronicle
SERVER_ID = 1
CHRONICLE = "ethernal"

# Map server IDs to their chronicle names
SERVER_NAMES = {
    1: "eternal",
    2: "interlude",
    10: "lu4",
    11: "lu4"
}

# --- CLI arguments ---
parser = argparse.ArgumentParser(description="Scrape MW2 Wiki races and classes.")
parser.add_argument("--server", type=int, default=SERVER_ID, help="Server ID (default: 10)")
parser.add_argument("--chronicle", type=str, default="", help="Chronicle code (optional; auto from server)")
args = parser.parse_args()

# Determine final chronicle value
SERVER_ID = args.server
CHRONICLE = args.chronicle or SERVER_NAMES.get(SERVER_ID, "lu4")

# --- Helpers ---
def clean_url(url: str) -> str:
    """Remove query strings like '?2' or '?v=3' from image URLs."""
    return re.sub(r'\?.*$', '', url)

def switch_server(driver, wait, server_id, chronicle):
    """Switch server and chronicle using CSRF-protected POST requests."""
    print(f"🔄 Switching to server {server_id} ({chronicle})...")

    # Get CSRF token
    csrf_token = driver.execute_script("""
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : null;
    """)

    if not csrf_token:
        print("❌ CSRF token not found. Make sure you're logged in or on the main wiki page.")
        return False

    # Execute JavaScript that performs both POSTs synchronously and waits for responses
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

    # Wait for reload and confirmation of switch
    try:
        print("⏳ Waiting for page reload...")
        time.sleep(4)
        wait.until(lambda d: chronicle.lower() in d.page_source.lower())
        print(f"✅ Switched successfully to server {server_id} ({chronicle}).")
        return True
    except Exception:
        print("⚠️ Switch may not have taken effect.")
        return False


# --- Setup Selenium ---
options = Options()
# options.add_argument("--headless")  # Uncomment for headless mode
options.add_argument("--log-level=3")
options.add_argument("--no-sandbox")
#options.add_argument("--disable-dev-shm-usage")
#options.add_argument("--blink-settings=imagesEnabled=false")
#options.add_argument("--disable-blink-features=AutomationControlled")
#options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
#options.add_argument("--disable-extensions")
#options.add_argument("--disable-background-networking")
#options.add_argument("--disable-sync")

driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)

# --- STEP 1: Open page ---
print(f"🌐 Opening races page ({CHRONICLE})...")
driver.get(INPUT_URL)
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#races-row")))
time.sleep(1)

# --- STEP 2: Switch server + chronicle ---
switch_server(driver, wait, SERVER_ID, CHRONICLE)

# --- STEP 3: Reload the page after switch ---
print("🔁 Reloading page after context switch...")
driver.get(f"{INPUT_URL}?chronicles={CHRONICLE}")
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#races-row")))
time.sleep(1)

# --- STEP 4: Parse data ---
print("🔍 Parsing races and subtypes...")
soup = BeautifulSoup(driver.page_source, "html.parser")
driver.quit()

rows = []
for race_div in soup.select("div#races-row > div.race"):
    race_name = race_div.select_one(".race-name p").get_text(strip=True)
    race_icon = race_div.select_one(".race-name img")["src"]
    race_icon = clean_url(BASE_URL + race_icon if race_icon.startswith("/") else race_icon)

    style = race_div.get("style", "")
    bg_match = re.search(r'url\((.*?)\)', style)
    race_bg = clean_url(BASE_URL + bg_match.group(1)) if bg_match else ""

    for a in race_div.select(".race-row a.race-type"):
        subtype_name = a.select_one("span").get_text(strip=True)
        subtype_link = a["href"]
        subtype_link = BASE_URL + subtype_link if subtype_link.startswith("/") else subtype_link

        sub_style = a.get("style", "")
        sub_bg_match = re.search(r'url\((.*?)\)', sub_style)
        subtype_bg = clean_url(BASE_URL + sub_bg_match.group(1)) if sub_bg_match else ""

        rows.append({
            "race_name": race_name,
            "race_icon": race_icon,
            "race_background": race_bg,
            "subtype_name": subtype_name,
            "subtype_background": subtype_bg,
            "subtype_link": subtype_link,
            "chronicle": CHRONICLE,
            "server_id": SERVER_ID
        })

# --- STEP 5: Save results ---
df = pd.DataFrame(rows)
df.to_csv(OUTPUT_FILE, sep="\t", index=False)
print(f"✅ Saved {len(df)} entries to {OUTPUT_FILE}")

# --- Optional GUI viewer ---
try:
    from pandasgui import show
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

print("🏁 Done.")
