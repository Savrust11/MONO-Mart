import openpyxl
import sys

def read_excel_first_sheet(filepath):
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        sheet = wb.active
        
        print(f"Sheet name: {sheet.title}")
        print()
        
        # Get all rows as lists
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(row)
        
        if rows:
            # Print column headers (first row)
            headers = rows[0]
            print(f"Columns ({len(headers)}): {headers}")
            print()
            
            # Print first 5 data rows
            print("First 5 data rows:")
            for i, row in enumerate(rows[1:6], 1):
                print(f"Row {i}: {row}")
        
        print(f"\nTotal rows (including header): {len(rows)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        read_excel_first_sheet(sys.argv[1])
