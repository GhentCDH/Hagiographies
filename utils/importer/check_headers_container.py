
from openpyxl import load_workbook
import os

f = '/data/hagiographies.xlsx'
if not os.path.exists(f):
    print(f"File not found: {f}")
    exit(1)

wb = load_workbook(f, read_only=True, data_only=True)
ws = wb['Manuscripts']
header_row = next(ws.rows)
headers = [str(c.value).strip() if c.value else 'None' for c in header_row]

print("--- START HEADERS ---")
for i, h in enumerate(headers):
    print(f"{i}: {h}")
print("--- END HEADERS ---")
