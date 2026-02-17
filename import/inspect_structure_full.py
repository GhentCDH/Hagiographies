import pandas as pd
import os

file_path = os.path.join(os.path.dirname(__file__), '../data/hagiographies.xlsx')
xls = pd.ExcelFile(file_path)

print("--- Reading Full Sheets ---")
# Use header=0 for Manuscripts as verified
df_ms = pd.read_excel(xls, sheet_name='Manuscripts', header=0)
df_ed = pd.read_excel(xls, sheet_name='Editions') # header=0 default

print(f"Manuscripts Rows: {len(df_ms)}")
print(f"Editions Rows: {len(df_ed)}")

# Collect all MS USED values from Editions
ms_used_cols = [c for c in df_ed.columns if str(c).startswith('MS USED')]
print(f"MS USED columns({len(ms_used_cols)}): {ms_used_cols}")

all_ms_used = set()
for col in ms_used_cols:
    vals = df_ed[col].dropna().astype(str).str.strip().unique()
    all_ms_used.update(vals)

print(f"Total unique MS USED references: {len(all_ms_used)}")
sorted_ms_used = sorted(list(all_ms_used))
print(f"First 20 MS USED references: {sorted_ms_used[:20]}")

# Collect Candidate IDs from Manuscripts
# 1. Unique ID (Col K) -> 'Unique ID'
col_unique_id = 'Unique ID'
if col_unique_id in df_ms.columns:
    ms_unique_ids = df_ms[col_unique_id].dropna().astype(str).str.strip().unique()
    print(f"Unique IDs in Manuscripts: {len(ms_unique_ids)}")
    intersection_unique = all_ms_used & set(ms_unique_ids)
    print(f"Intersection with Unique ID: {len(intersection_unique)}")
    if intersection_unique:
        print(f"Examples: {list(intersection_unique)[:5]}")
else:
    print(f"Column '{col_unique_id}' not found in Manuscripts")

# 2. Unique identifier per collection (Col 11) -> 'Unique  identifier per collection'
# Inspect column names to find it
col_collection = None
for c in df_ms.columns:
    if 'collection' in str(c) and 'identifier' in str(c):
        col_collection = c
        break
        
if col_collection:
    print(f"Using column for collection: '{col_collection}'")
    ms_collection_ids = df_ms[col_collection].dropna().astype(str).str.strip().unique()
    print(f"Collection IDs in Manuscripts: {len(ms_collection_ids)}")
    intersection_collection = all_ms_used & set(ms_collection_ids)
    print(f"Intersection with Collection ID: {len(intersection_collection)}")
    if intersection_collection:
        print(f"Examples: {list(intersection_collection)[:5]}")

# 3. Shelfmark
col_shelf = 'Shelfmark'
if col_shelf in df_ms.columns:
    ms_shelf = df_ms[col_shelf].dropna().astype(str).str.strip().unique()
    print(f"Shelfmarks in Manuscripts: {len(ms_shelf)}")
    intersection_shelf = all_ms_used & set(ms_shelf)
    print(f"Intersection with Shelfmark: {len(intersection_shelf)}")
    if intersection_shelf:
        print(f"Examples: {list(intersection_shelf)[:5]}")
