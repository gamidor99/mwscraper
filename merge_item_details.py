import pandas as pd
import glob

# --- Find all checkpoint files ---
files = glob.glob("items_details_checkpoint*.tsv")
if not files:
    raise SystemExit("❌ No checkpoint files found!")

print(f"📂 Found {len(files)} checkpoint files:")
for f in files:
    print("  -", f)

# --- Count total rows before merging ---
total_rows = 0
for f in files:
    df_tmp = pd.read_csv(f, sep="\t")
    rows = len(df_tmp)
    total_rows += rows
    print(f"   📄 {f}: {rows} rows")

print(f"\n📊 Total rows BEFORE merge: {total_rows}")

# --- Merge all ---
df_list = [pd.read_csv(f, sep="\t") for f in files]
df_out = pd.concat(df_list, ignore_index=True)

# --- Deduplicate by item_id ---
unique_before = len(df_out)
df_out = df_out.drop_duplicates(subset=["item_id"], keep="last")
unique_after = len(df_out)

print(f"✅ Total combined rows: {unique_before}")
print(f"✅ Unique items after deduplication: {unique_after}")
print(f"🗑️ Removed {unique_before - unique_after} duplicate entries")

# --- Preview with pandasgui ---
try:
    from pandasgui import show
    print("\n📊 Opening GUI preview... (close it to continue)")
    gui = show(df_out, settings={'block': True})
except ImportError:
    print("⚠️ pandasgui not installed. Install with: pip install pandasgui")

# --- Save final merged file ---
output_file = "items_details_merged.tsv"
df_out.to_csv(output_file, sep="\t", index=False)
print(f"\n💾 Merged {unique_after} unique items saved to: {output_file}")
