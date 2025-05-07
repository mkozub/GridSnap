import os
import base64
import json
from io import BytesIO
from PIL import Image
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import smartsheet
import pkg_resources

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__, static_folder="static")

# Initialize API clients
try:
    # Gemini API setup
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
    # Updated to use the faster Flash model
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Smartsheet API setup
    SMARTSHEET_API_TOKEN = os.getenv("SMARTSHEET_API_TOKEN")
    smartsheet_client = smartsheet.Smartsheet(SMARTSHEET_API_TOKEN)
    # Ensure we don't retry API calls too aggressively
    smartsheet_client.errors_as_exceptions(True)
except Exception as e:
    print(f"Error initializing APIs: {e}")

# Smartsheet column types
SMARTSHEET_COLUMN_TYPES = [
    "TEXT_NUMBER",
    "DATE",
    "DATETIME",
    "CONTACT_LIST",
    "CHECKBOX",
    "PICKLIST",
    "DURATION"
]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/verify-sheet", methods=["POST"])
def verify_sheet():
    sheet_id = request.json.get("sheet_id")
    
    if not sheet_id:
        return jsonify({"valid": False, "message": "Sheet ID is required"}), 400
    
    try:
        # Try to get the sheet to verify it exists and is accessible
        sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
        return jsonify({
            "valid": True, 
            "sheet_name": sheet.name,
            "message": f"Sheet '{sheet.name}' is valid and accessible"
        })
    except Exception as e:
        return jsonify({
            "valid": False, 
            "message": f"Error verifying sheet: {str(e)}"
        }), 400

@app.route("/extract-headers", methods=["POST"])
def extract_headers():
    try:
        # Get form data
        image_file = request.files.get("image")
        
        if not image_file:
            return jsonify({"error": "No image uploaded"}), 400
        
        # Process image
        image_data = Image.open(image_file)
        
        # Convert to format Gemini API expects
        buffer = BytesIO()
        image_data.save(buffer, format=image_data.format)
        image_bytes = buffer.getvalue()
        image_parts = [
            {
                "mime_type": f"image/{image_data.format.lower()}",
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        ]
        
        # Prepare prompt for Gemini
        prompt = """
            You are an expert in extracting data from images of tables and grids.
            Your task is to extract ONLY the column headers from the top row of a data table, and for each header, infer the most likely data type based on the visible content in that column.

            Rules:
            1. Ignore any application UI elements such as ribbon bars, toolbars, or menus (e.g., 'File', 'Edit', etc.).
            2. Focus ONLY on the actual column headers directly above the grid of structured data (e.g., 'Task Name', 'Start', 'Finish').
            3. For each header, return an object with two properties: 'name' (the exact header text) and 'type' (the inferred type: one of "TEXT_NUMBER", "DATE", "DATETIME", "CONTACT_LIST", "CHECKBOX", "PICKLIST", "DURATION")
                - If cells in the column contain valid dates, use 'DATE'.
                - If cells contain date and time values, use 'DATETIME'.
                - If cells contain names or emails, use 'CONTACT_LIST'.
                - If cells contain only numbers or text, use 'TEXT_NUMBER'.
                - If cells contain repeated values from a set, use 'PICKLIST'.
                - If cells contain Yes/No, checkmarks, or boxes, use 'CHECKBOX'.
                - If cells represent time durations (e.g., "3h", "45m"), use 'DURATION'.
            5. Preserve the exact text of the headers as seen in the image.
            6. Do not include any explanations or non-header elements in the output.
            7. If no table is visible, return an error.

            Example output:
            [
              { "name": "Start Date", "type": "date" },
              { "name": "Assigned To", "type": "contact" },
              { "name": "Complete?", "type": "checkbox" }
            ]
        """
        
        # Call Gemini API
        response = gemini_model.generate_content(
            [prompt, image_parts[0]],
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95
            }
        )
        
        # Process response
        response_text = response.text
        
        print(response_text)

        # Ensure we have a JSON response by extracting from markdown code blocks if needed
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
            
        try:
            # Validate JSON
            headers = json.loads(response_text)
            if not isinstance(headers, list) or not all(isinstance(h, dict) and "name" in h and "type" in h for h in headers):
                return jsonify({"error": "Invalid header format detected. Each header must have 'name' and 'type'."}), 400
            return jsonify({"headers": headers})
        except json.JSONDecodeError:
            return jsonify({
                "error": "Failed to parse Gemini response as JSON",
                "raw_response": response_text
            }), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/process-image", methods=["POST"])
def process_image():
    print("[process_image] Called")
    try:
        # Get form data
        image_file = request.files.get("image")
        context = request.form.get("context", "")
        headers = json.loads(request.form.get("headers", "[]"))
        print(f"[process_image] Received image: {bool(image_file)}, context: {context}, headers: {headers}")
        
        if not image_file:
            print("[process_image] No image uploaded")
            return jsonify({"error": "No image uploaded"}), 400
        
        # Process image
        image_data = Image.open(image_file)
        print("[process_image] Image opened successfully")
        
        # Convert to format Gemini API expects
        buffer = BytesIO()
        image_data.save(buffer, format=image_data.format)
        image_bytes = buffer.getvalue()
        image_parts = [
            {
                "mime_type": f"image/{image_data.format.lower()}",
                "data": base64.b64encode(image_bytes).decode("utf-8")
            }
        ]
        print("[process_image] Image converted for Gemini API")
        
        # Refined prompt for Gemini
        column_instructions = '\n'.join([f'- {h["name"]}: {h["type"]}' for h in headers])
        prompt = f"""
        You are an expert in extracting data from images of tables and grids.
        Return a structured JSON array containing every row visible in the table from the screenshot. Each row should include values for all the detected column headers. Format each item as a dictionary with keys matching the header names.

        Use these columns and types:
        {column_instructions}

        Rules:
        1. Extract ALL visible rows and columns in the table, preserving row and column structure.
        2. Return ONLY a valid JSON array of objects, where each object represents a row.
        3. Use the correct format for each column type as specified above.
        4. For empty cells, use null as the value.
        5. Preserve the data types (numbers should be numbers, text as text).
        6. If there is no clear structured data in the image, return an error.
        7. Do not include any explanations, extra text, or markdown formatting—just the JSON array.
        8. For columns of type DATE, always return dates in the format YYYY-MM-DD (ISO 8601).
        9. For columns of type DATETIME, always return datetimes in the format YYYY-MM-DDTHH:MM:SSZ (ISO 8601, UTC).
        10. If a column is of type CONTACT_LIST, return an email address for each value. If no real email is visible, use a placeholder in the format visible_name@example.com. Ensure the output is a valid email format with no spaces.
        Additional context: {context}
        """
        print("[process_image] Calling Gemini API...")
        # Call Gemini API
        response = gemini_model.generate_content(
            [prompt, image_parts[0]],
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95
            }
        )
        print("[process_image] Gemini API call complete")
        
        # Process response
        response_text = response.text
        print(f"[process_image] Gemini response: {response_text[:200]}")
        
        # Ensure we have a JSON response by extracting from markdown code blocks if needed
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```" )[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```" )[1].split("```" )[0].strip()
        
        try:
            # Validate JSON
            parsed_data = json.loads(response_text)
            print(f"[process_image] Parsed data: {str(parsed_data)[:200]}")
            # Ensure parsed_data is a list of rows
            if not isinstance(parsed_data, list):
                print("[process_image] Gemini did not return a list of rows")
                return jsonify({"error": "Gemini did not return a list of rows. Please try again or check the image quality.", "raw_response": response_text}), 500
            if len(parsed_data) == 0:
                print("[process_image] Gemini returned an empty list")
                return jsonify({"error": "No rows found in the image.", "raw_response": response_text}), 500
            print("[process_image] Returning success response")
            # Also print to frontend for debugging
            return jsonify({"data": parsed_data, "debug": parsed_data})
        except json.JSONDecodeError:
            print("[process_image] Failed to parse Gemini response as JSON")
            return jsonify({
                "error": "Failed to parse Gemini response as JSON",
                "raw_response": response_text
            }), 500
        
    except Exception as e:
        print(f"[process_image] Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/update-column-headers", methods=["POST"])
def update_column_headers():
    sheet_id = request.json.get("sheet_id")
    headers = request.json.get("headers")
    
    if not sheet_id or not headers:
        return jsonify({"error": "Sheet ID and headers are required"}), 400
    
    try:
        print(f"Updating column headers for sheet {sheet_id}")  # Debug log
        
        # Get current sheet
        sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
        
        # Delete all columns except the first one (which we can't delete)
        if len(sheet.columns) > 1:
            # We need to delete columns one at a time
            for column in sheet.columns[1:]:  # Skip the first column
                print(f"Deleting column: {column.title} (ID: {column.id})")  # Debug log
                smartsheet_client.Sheets.delete_column(sheet_id, column.id)
        
        # Create new columns - all with index 1 (insert after primary column)
        new_columns = []
        for header in headers:
            new_columns.append({
                "title": header["name"],
                "type": header["type"],
                "index": 1,
                "primary": False
            })
        
        print(f"Adding new columns: {new_columns}")  # Debug log
        
        # Add new columns
        added_columns = smartsheet_client.Sheets.add_columns(sheet_id, new_columns)
        
        return jsonify({
            "success": True,
            "message": f"Successfully updated {len(new_columns)} column headers",
            "columns": [{"id": col.id, "title": col.title} for col in added_columns.data]
        })
        
    except Exception as e:
        print(f"Error updating column headers: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

@app.route("/update-sheet", methods=["POST"])
def update_sheet():
    sheet_id = request.json.get("sheet_id")
    data = request.json.get("data")
    print(f"[update_sheet] Called. Smartsheet SDK version: {pkg_resources.get_distribution('smartsheet-python-sdk').version}")
    print(f"[update_sheet] Data to push: {json.dumps(data, indent=2)}")
    
    if not sheet_id or not data:
        return jsonify({"error": "Sheet ID and data are required"}), 400
    
    try:
        # Get current sheet to understand the structure
        sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
        
        # Create column ID mapping
        column_map = {col.title: col.id for col in sheet.columns}
        print(f"[update_sheet] Column map: {column_map}")
        
        # Clear existing rows
        if sheet.total_row_count > 0:
            row_ids = [row.id for row in sheet.rows]
            if row_ids:
                smartsheet_client.Sheets.delete_rows(sheet_id, row_ids)
        
        # Prepare new rows using Smartsheet SDK models directly
        new_rows = []
        for row_data in data:
            # Create a new row using the SDK
            new_row = smartsheet.models.Row()
            new_row.to_bottom = True
            
            # Track if we have at least one non-empty cell
            has_content = False
            
            # Add cells to the row
            for col_title, col_id in column_map.items():
                # Get the value from the data, using empty string as default for None
                value = row_data.get(col_title, "")
                
                # Log the value
                print(f"[update_sheet] Adding cell: column_id={col_id}, value={value}")
                
                # Create a new cell with the value, ensuring it's never None
                # For primary column, make sure we have at least an empty string
                if value is None:
                    value = ""
                
                if value != "":
                    has_content = True
                
                # Create and add the cell
                new_cell = smartsheet.models.Cell()
                new_cell.column_id = col_id
                new_cell.value = value
                new_row.cells.append(new_cell)
            
            # Only add non-empty rows
            if has_content:
                new_rows.append(new_row)
                print(f"[update_sheet] Adding row with {len(new_row.cells)} cells")
            else:
                print("[update_sheet] Skipping empty row")
        
        print(f"[update_sheet] Final payload: {len(new_rows)} rows to be sent to Smartsheet")
        
        # Add rows to sheet (in batches if many rows)
        if new_rows:
            batch_size = 100  # Smartsheet recommends adding in batches
            for i in range(0, len(new_rows), batch_size):
                batch = new_rows[i:i+batch_size]
                print(f"[update_sheet] Pushing batch of {len(batch)} rows")
                result = smartsheet_client.Sheets.add_rows(sheet_id, batch)
                print(f"[update_sheet] Batch result: {result}")
        
        return jsonify({
            "success": True,
            "message": f"Successfully added {len(new_rows)} rows",
            "row_count": len(new_rows)
        })
        
    except Exception as e:
        print(f"[update_sheet] Exception: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
