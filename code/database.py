import json
import time
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

def save_interview_to_sheet(interview_id, student_id, name, company, interview_type, timestamp, transcript, duration):
    """
    Appends a new row to the 'Interviews' sheet in your Google Sheets database.
    
    Expected columns:
      A: Interview ID  
      B: Student ID  
      C: Name  
      D: Company  
      E: Interview Type  
      F: Timestamp  
      G: Transcript  
      H: Duration (minutes)
    """
    # Retrieve the service account info from st.secrets
    service_account_info = json.loads(st.secrets["SERVICE_ACCOUNT_JSON"])
    if "\\n" in service_account_info["private_key"]:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=scopes)
    sheets_service = build("sheets", "v4", credentials=credentials)
    
    # Get the spreadsheet ID from st.secrets or replace with your actual ID
    spreadsheet_id = st.secrets.get("SPREADSHEET_ID", "1C-ZiMt48h7Wv4y1gDkFbBM4rzwgBFOCDVqpa8vtqWfI")
    
    # Prepare the new row data as a list of lists
    new_row = [[
        interview_id,
        student_id,
        name,
        company,
        interview_type,
        timestamp,
        transcript,
        duration
    ]]
    
    # Define the target range (sheet "Interviews", columns A:H)
    range_name = "Interviews!A:H"
    body = {"values": new_row}
    
    result = sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()
    
    st.write(f"Saved interview data to Google Sheets: {result.get('updates', {}).get('updatedCells', 0)} cells updated.")

def update_progress_sheet(student_id, name, interview_type, completion_date):
    """
    Checks the "Progress" sheet and updates or appends a row based on the student ID.
    
    Expected sheet structure (columns):
      A: Student ID  
      B: Name  
      C: Default  
      D: midterm_interview  
      E: End Reflection Completed  
      F: Last Updated
     
    If the student already exists:
      - Update the cell in the column corresponding to the interview_type (e.g., "Default", "midterm_interview", "End Reflection Completed")
      - Update the "Last Updated" column with the completion_date.
    If the student does not exist:
      - Append a new row with student ID, Name, the appropriate interview type column set to completion_date, and "Last Updated" set to completion_date.
    """
    # Retrieve the service account info from st.secrets
    service_account_info = json.loads(st.secrets["SERVICE_ACCOUNT_JSON"])
    if "\\n" in service_account_info["private_key"]:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=scopes)
    sheets_service = build("sheets", "v4", credentials=credentials)
    
    spreadsheet_id = st.secrets.get("SPREADSHEET_ID", "1C-ZiMt48h7Wv4y1gDkFbBM4rzwgBFOCDVqpa8vtqWfI")
    
    # Define the range to read from the "Progress" sheet (assumes header is in row 1)
    range_name = "progress!A:F"
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range_name
    ).execute()
    values = result.get("values", [])
    
    # Define mapping for interview types to column index (0-indexed, header row excluded)
    column_map = {
        "Default": 2,                # Column C
        "midterm_interview": 3,      # Column D
        "End Reflection Completed": 4  # Column E
    }
    
    updated = False
    row_index = None  # This will be the index in the 'values' list (header is at index 0)
    
    # Skip header (first row) when searching
    for i, row in enumerate(values[1:], start=1):
        if row and row[0] == student_id:
            row_index = i
            # Update Name in case it changed
            if len(row) < 2:
                row.append(name)
            else:
                row[1] = name
            # Ensure the row has at least 6 columns (A:F)
            while len(row) < 6:
                row.append("")
            # Update the corresponding interview type cell if present
            if interview_type in column_map:
                col_idx = column_map[interview_type]
                row[col_idx] = completion_date
            # Update the Last Updated column (index 5)
            row[5] = completion_date
            updated = True
            break
    
    if updated and row_index is not None:
        # Update the specific row in the sheet.
        update_range = f"Progress!A{row_index+1}:F{row_index+1}"
        body = {"values": [values[row_index]]}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=update_range,
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        st.write(f"Updated progress for student {student_id} in row {row_index+1}.")
    else:
        # Student not found; create a new row.
        # Prepare a new row with empty strings for columns that are not updated.
        new_row = [student_id, name, "", "", "", ""]
        if interview_type in column_map:
            col_idx = column_map[interview_type]
            new_row[col_idx] = completion_date
        new_row[5] = completion_date  # Last Updated column
        append_range = "Progress!A:F"
        body = {"values": [new_row]}
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=append_range,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
        st.write(f"Appended new progress row for student {student_id}.")
        
def get_transcript_by_student_and_type(student_id, target_interview_type):
    """
    Retrieves the transcript from the 'Interviews' sheet for a given student_id and interview type.
    Returns the transcript string if found, otherwise returns an empty string.
    Assumes the "Interviews" sheet has the following columns:
      A: Interview ID, B: Student ID, C: Name, D: Company, E: Interview Type,
      F: Timestamp, G: Transcript, H: Duration.
    """
    service_account_info = json.loads(st.secrets["SERVICE_ACCOUNT_JSON"])
    if "\\n" in service_account_info["private_key"]:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=scopes)
    sheets_service = build("sheets", "v4", credentials=credentials)
    
    spreadsheet_id = st.secrets.get("SPREADSHEET_ID", "1C-ZiMt48h7Wv4y1gDkFbBM4rzwgBFOCDVqpa8vtqWfI")
    # Read all rows from the "Interviews" sheet
    range_name = "Interviews!A:H"
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name
    ).execute()
    values = result.get("values", [])
    
    transcript = ""
    # Assume first row is a header; iterate over the remaining rows
    for row in values[1:]:
        # Check if the row has the expected number of columns (at least 7)
        if len(row) >= 7:
            # row[1] is Student ID, row[4] is Interview Type, row[6] is Transcript
            if row[1] == student_id and row[4].lower() == target_interview_type.lower():
                transcript = row[6]
                break
    return transcript