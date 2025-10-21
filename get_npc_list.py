from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import pandas as pd

# --- CONFIG ---
LIMIT = 5000          # total results limit in query
PER_PAGE = 5000       # results per page
MAX_PAGES = 10      # 0 = all pages, or limit to N pages
SLEEP_BETWEEN = 2   # seconds between requests
SLEEP_END = 5       # seconds before exit

BASE_URL = (
    "https://wiki.mw2.wiki/search/npc?"
    "query=&sub%5BlevelMin%5D=1&sub%5BlevelMax%5D=99&sub%5Brace%5D="
    "&page={page}&limit=" + str(LIMIT) + "&per-page=" + str(PER_PAGE)
)

# --- Setup Selenium ---
options = Options()

# options.add_argument("--headless")       # ❌ Commented out to show the browser
options.add_argument("--log-level=3")      # ✅ Suppress most browser console logs
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)

all_npcs = []
page = 1

while True:
    url = BASE_URL.format(page=page)
    print(f"📄 Scraping page {page}: {url}")
    driver.get(url)
    time.sleep(SLEEP_BETWEEN)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", class_="table-vcenter")
    if not table:
        print("⚠️ No table found — stopping.")
        break

    rows = table.select("tbody tr")
    if not rows:
        print("✅ No rows found — done.")
        break

    for row in rows:
        a_tag = row.select_one("a.item-name")
        name_el = row.select_one(".item-name__content")
        level_el = row.select_one(".item-name__additional")

        if a_tag and name_el and level_el:
            name = name_el.contents[0].strip()
            level_raw = level_el.get_text(strip=True)
            level_clean = level_raw.replace("Lv.", "").strip()
            href = a_tag.get("href", "").strip()
            full_url = f"https://wiki.mw2.wiki{href}"

            all_npcs.append({
                "name": name,
                "level": int(level_clean),
                "url": full_url
            })
            print(f"  ➤ {name} — {level_clean} — {full_url}")

    if MAX_PAGES > 0 and page >= MAX_PAGES:
        print(f"🏁 Reached page limit ({MAX_PAGES}).")
        break

    pagination = soup.select_one("ul.pagination li.next a")
    if not pagination:
        print("🏁 Finished: no more pages.")
        break

    page += 1

# --- Save results ---
df = pd.DataFrame(all_npcs)
df.to_csv("npc_list.csv", index=False, encoding="utf-8")
print(f"✅ Done! Scraped {len(all_npcs)} NPCs. Results saved to npc_list.csv")

# --- Optional GUI ---
try:
    from pandasgui import show
    print("📊 Opening pandas GUI...")
    show(df)
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")
    print(df.head())

# --- Sleep & exit ---
print(f"⏳ Sleeping {SLEEP_END} seconds before exit...")
time.sleep(SLEEP_END)
input("🔚 Press Enter to exit...")

driver.quit()
