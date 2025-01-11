from flask import Flask, request, render_template, redirect, url_for, send_file, flash
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Color
import os
import warnings
import copy

app = Flask(__name__)
app.secret_key = "secret"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Constants
MOVING_ARM_KEYWORD = "Moving Arm"
FIXED_ARM_KEYWORD = "Fixed Arm"
CONSOLE_KEYWORD = "Console"
TAB_COLOR_COMPLETE = Color(rgb="FF00FF00")
TAB_COLOR_PARTIAL = Color(rgb="FF800080")
TAB_COLOR_MISSING = Color(rgb="FFFF0000")
LOG_FILE = "process_log.txt"

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# Helper function to update log
def update_log(message):
    with open(LOG_FILE, "a") as log_file:
        log_file.write(message + "\n")

# Clear log file on startup
def clear_log_file():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w") as log_file:
            log_file.write("=== Log Cleared on Startup ===\n")

# Find section row
def find_section_row(target_sheet, section_keyword):
    for row in range(1, target_sheet.max_row + 1):
        cell_value = target_sheet.cell(row=row, column=7).value
        if isinstance(cell_value, str) and section_keyword.lower() in cell_value.lower():
            return row
    return None

# Remove empty rows
def remove_empty_rows(sheet, start_row, max_blank_rows=1):
    current_row = start_row + 1
    while current_row <= sheet.max_row:
        g_value = sheet.cell(row=current_row, column=7).value
        if g_value:
            break
        row_values = [sheet.cell(row=current_row, column=col).value for col in range(1, sheet.max_column + 1)]
        if not any(row_values):
            sheet.delete_rows(current_row)
        else:
            current_row += 1
    blank_row_count = 0
    while current_row <= sheet.max_row:
        row_values = [sheet.cell(row=current_row, column=col).value for col in range(1, sheet.max_column + 1)]
        if any(row_values):
            break
        blank_row_count += 1
        if blank_row_count > max_blank_rows:
            sheet.delete_rows(current_row)
        else:
            current_row += 1

# Copy data exactly
def copy_data_exactly(source_sheet, target_sheet, target_start_row):
    for source_row in source_sheet.iter_rows(min_row=1, max_row=source_sheet.max_row):
        target_row_index = target_start_row + source_row[0].row - 1
        for source_cell in source_row:
            target_cell = target_sheet.cell(row=target_row_index, column=source_cell.column)
            target_cell.value = source_cell.value
            if source_cell.has_style:
                target_cell.font = copy.copy(source_cell.font)
                target_cell.border = copy.copy(source_cell.border)
                target_cell.fill = copy.copy(source_cell.fill)
                target_cell.number_format = source_cell.number_format
                target_cell.protection = copy.copy(source_cell.protection)
                target_cell.alignment = copy.copy(source_cell.alignment)
    for merged_cell_range in source_sheet.merged_cells.ranges:
        target_sheet.merge_cells(str(merged_cell_range))

# Process equipment file
def process_equipment(equipment_file, converted_files, main_file):
    equipment_df = pd.read_excel(equipment_file)
    equipment_df = equipment_df[equipment_df['MachineNumber'].str.startswith('5', na=False)]
    main_wb = load_workbook(main_file)

    for _, row in equipment_df.iterrows():
        machine_number = row['MachineNumber']
        target_sheet_name = f"GA-{machine_number}"

        if target_sheet_name not in main_wb.sheetnames:
            update_log(f"Location {target_sheet_name}: Not found. Skipping.")
            continue

        target_sheet = main_wb[target_sheet_name]
        for converted_file in converted_files:
            converted_wb = load_workbook(converted_file)
            for sheet_name in converted_wb.sheetnames:
                source_sheet = converted_wb[sheet_name]
                section_start = find_section_row(target_sheet, sheet_name)
                if section_start:
                    copy_data_exactly(source_sheet, target_sheet, section_start)

    main_wb.save(main_file)
    update_log("Processing complete.")

# Flask routes
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        equipment_file = request.files['equipment_file']
        converted_files = request.files.getlist('converted_files')
        main_file = request.files['main_file']

        equipment_path = os.path.join(UPLOAD_FOLDER, equipment_file.filename)
        main_path = os.path.join(UPLOAD_FOLDER, main_file.filename)
        converted_paths = [os.path.join(UPLOAD_FOLDER, f.filename) for f in converted_files]

        equipment_file.save(equipment_path)
        main_file.save(main_path)
        for file, path in zip(converted_files, converted_paths):
            file.save(path)

        process_equipment(equipment_path, converted_paths, main_path)
        flash("Processing complete.")
        return redirect(url_for('index'))

    return render_template('autobom.html')

@app.route('/download_log')
def download_log():
    return send_file(LOG_FILE, as_attachment=True)

@app.route('/clear_log')
def clear_log():
    clear_log_file()
    flash("Log cleared.")
    return redirect(url_for('index'))

if __name__ == '__main__':
    clear_log_file()
    app.run(debug=True)
