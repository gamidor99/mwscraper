# 🧩 MW2 Wiki Scraper Suite

A complete multi-module data scraper for [wikipedia1.mw2.wiki](https://wikipedia1.mw2.wiki) — designed to collect Lineage II game data across different **Chronicles** (e.g., `lu4`, `hf`, `gc`, `ethernal`, etc.).

Each module runs in two phases:

1. **_list** → collects base data (IDs, names, URLs)
2. **_details** → visits each entry and extracts detailed information

All data is exported as `.tsv` (tab-separated) files for easy import into databases, spreadsheets, or wiki systems.

---

## 🧰 Supported Categories

| Category | List Script | Details Script | Output Files |
|-----------|--------------|----------------|----------------|
| 💎 Items | `get_items_list.py` | `get_items_details.py` | `items_list.tsv`, `items_details.tsv` |
| ⚔️ Skills | `get_skills_list.py` | `get_skills_details.py` | `skills_list.tsv`, `skills_details.tsv` |
| 🧙‍♂️ NPCs | `get_npc_list.py` | `get_npc_details.py` | `npc_list.tsv`, `npc_details.tsv` |
| 📜 Quests | `get_quests_list.py` | `get_quests_details.py` | `quests_list.tsv`, `quests_details.tsv` |
| 🧪 Recipes | `get_recipes_list.py` | `get_recipes_details.py` | `recipes_list.tsv`, `recipes_details.tsv` |
| 🧬 Races / Classes | `get_races_classes_list.py` | — | `races.tsv` |

---

## ⚙️ Features

✅ Works on **Windows, macOS, and Linux**  
✅ Built with **Selenium** + **BeautifulSoup4**  
✅ Automatic **ChromeDriver management** via `webdriver_manager`  
✅ Optional **Chronicle filtering**  
✅ **Checkpoint resume** for long scrapes  
✅ Clean **TSV export** (tab-delimited)  
✅ Optional **pandasgui** table viewer  

---

## 📦 Requirements

- Python ≥ 3.10  
- Google Chrome (latest version)  
- Internet access  
- Optional: [Homebrew](https://brew.sh) for macOS, `apt` for Linux  

---

## 🧰 Environment Setup

### 🪟 **Windows**
```bash
# Navigate to your folder
cd C:\path\to\mwscraper

# Create virtual environment
python -m venv venv

# Activate environment
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt


### 🍎 **macOS / 🐧 Linux**
```bash
# Navigate to your project folder
cd /path/to/mwscraper

# Create a virtual environment
python3 -m venv venv

# Activate the environment
source venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
