import pandas as pd
import os

file_path = os.path.join(os.path.dirname(__file__), '../data/hagiographies.xlsx')
xls = pd.ExcelFile(file_path)

print("--- Manuscripts Sheet (Head with header=0) ---")
df_ms = pd.read_excel(xls, sheet_name='Manuscripts', header=0, nrows=5)
print(df_ms.to_string())

print("\n--- Editions Sheet (Head) ---")
df_ed = pd.read_excel(xls, sheet_name='Editions', nrows=5)
print(df_ed[['BHL ', 'Title', 'MS USED 1']].head().to_string())

# Collect all MS USED values
ms_used_cols = [c for c in df_ed.columns if 'MS USED' in c]
print(f"MS USED columns: {ms_used_cols}")

all_ms_used = set()
for col in ms_used_cols:
    vals = df_ed[col].dropna().astype(str).str.strip().unique()
    all_ms_used.update(vals)

print(f"Total unique MS USED references: {len(all_ms_used)}")
sorted_ms_used = sorted(list(all_ms_used))
print(f"Sample MS USED references: {sorted_ms_used[:20]}")

# Check Intersection with Unique ID
col_unique_id = 'Unique ID'
ms_unique_ids = df_ms[col_unique_id].dropna().astype(str).str.strip().unique()
intersection_unique = all_ms_used & set(ms_unique_ids)
print(f"Intersection with Unique ID: {len(intersection_unique)}")
if intersection_unique:
    print(f"Examples: {list(intersection_unique)[:10]}")

# Check Intersection with Collection ID
col_collection = 'Unique  identifier per collection'
ms_collection_ids = df_ms[col_collection].dropna().astype(str).str.strip().unique()
intersection_collection = all_ms_used & set(ms_collection_ids)
print(f"Intersection with Collection ID: {len(intersection_collection)}")
if intersection_collection:
    print(f"Examples: {list(intersection_collection)[:10]}")

# Check Intersection with Shelfmark
col_shelf = 'Shelfmark'
ms_shelf = df_ms[col_shelf].dropna().astype(str).str.strip().unique()
intersection_shelf = all_ms_used & set(ms_shelf)
print(f"Intersection with Shelfmark: {len(intersection_shelf)}")
if intersection_shelf:
    print(f"Examples: {list(intersection_shelf)[:10]}")

# Check Locations
print("\nUnique Locations in Manuscripts:")
print(df_ms['Location'].dropna().unique())
