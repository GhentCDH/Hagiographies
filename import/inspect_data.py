import pandas as pd
import os

# Define the path to the Excel file
file_path = os.path.join(os.path.dirname(__file__), '../data/hagiographies.xlsx')

print(f"Reading file: {file_path}")

try:
    # Read the Excel file
    xls = pd.ExcelFile(file_path)

    print(f"Sheet names: {xls.sheet_names}")

    # Define sheets to inspect (updated based on actual names if possible, but for now specific ones)
    t = ['Manuscripts', 'Editions', 'Corpus Hagio'] 
    
    # Check if 'Corpus Hagio' has a different name
    for sheet in xls.sheet_names:
        if 'Corpus' in sheet or 'Hagio' in sheet:
            if sheet not in t:
                t.append(sheet)

    for sheet_name in xls.sheet_names:
        # inspect all sheets briefly
        print(f"\n--- Inspecting contents of sheet: {sheet_name} ---")
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, nrows=50)
            print(f"Columns: {list(df.columns)}")
            print(f"Data Types:\n{df.dtypes}")
            print(f"\nFirst 5 rows:\n{df.head().to_string()}")
        except Exception as e:
            print(f"Error reading sheet {sheet_name}: {e}")

except Exception as e:
    print(f"Error reading Excel file: {e}")
