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
