import streamlit as st
import hmac
import time
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# Password screen for dashboard (note: only very basic authentication!)
# Based on https://docs.streamlit.io/knowledge-base/deploy/authentication-without-sso
def check_password():
    """Returns 'True' if the user has entered a correct password."""

    def login_form():
        """Form with widgets to collect user information"""
        with st.form("Credentials"):
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.form_submit_button("Log in", on_click=password_entered)

    def password_entered():
        """Checks whether username and password entered by the user are correct."""
        if st.session_state.username in st.secrets.passwords and hmac.compare_digest(
            st.session_state.password,
            st.secrets.passwords[st.session_state.username],
        ):
            st.session_state.password_correct = True

        else:
            st.session_state.password_correct = False

        del st.session_state.password  # don't store password in session state

    # Return True, username if password was already entered correctly before
    if st.session_state.get("password_correct", False):
        return True, st.session_state.username

    # Otherwise show login screen
    login_form()
    if "password_correct" in st.session_state:
        st.error("User or password incorrect")
    return False, st.session_state.username


def check_if_interview_completed(directory, username):
    """Check if interview transcript/time file exists which signals that interview was completed."""

    # Test account has multiple interview attempts
    if username != "testaccount":

        # Check if file exists
        try:
            with open(os.path.join(directory, f"{username}.txt"), "r") as _:
                return True

        except FileNotFoundError:
            return False

    else:

        return False


def save_interview_data(folder_id, student_number, company_name):
    """Save interview data locally and upload to Google Drive with correct file naming."""

    # Get current date in YYMMDD format
    current_date = time.strftime("%y%m%d")

    # Sanitize company name to remove spaces and special characters
    sanitized_company = "".join(c for c in company_name if c.isalnum())

    # Construct the file names
    transcript_filename = f"{current_date}_{student_number}_{sanitized_company}_transcript.txt"
    time_filename = f"{current_date}_{student_number}_{sanitized_company}_time.txt"
    
    # Ensure directories exist
    os.makedirs(transcripts_directory, exist_ok=True)
    os.makedirs(times_directory, exist_ok=True)

    # Define file paths
    transcript_file = os.path.join(transcripts_directory, transcript_filename)
    time_file = os.path.join(times_directory, time_filename)

    # Save transcript
    with open(transcript_file, "w") as t:
        t.write(f"Session ID: {st.session_state.session_id}\n\n")
        for message in st.session_state.messages[1:]:
            t.write(f"{message['role']}: {message['content']}\n")

    # Save interview timing data
    with open(time_file, "w") as d:
        duration = (time.time() - st.session_state.start_time) / 60
        d.write(
            f"Session ID: {st.session_state.session_id}\n"
            f"Start time (UTC): {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(st.session_state.start_time))}\n"
            f"Interview duration (minutes): {duration:.2f}"
        )

    # Upload files to Google Drive
    transcript_link = upload_to_google_drive(transcript_file, transcript_filename, folder_id)
    time_link = upload_to_google_drive(time_file, time_filename, folder_id)

    return transcript_link  # Return Google Drive link for sharing
        
def upload_to_google_drive(file_path, file_name, folder_id):
    """Uploads a file to Google Drive, overwriting an existing one if found."""

    # Retrieve and parse the JSON from Streamlit secrets
    service_account_info = json.loads(st.secrets["SERVICE_ACCOUNT_JSON"])

    # Ensure the private_key is correctly formatted
    if "\\n" in service_account_info["private_key"]:
        service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

    # Authenticate with Google Drive
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    service = build("drive", "v3", credentials=credentials)

    # Step 1: Search for existing file in the folder
    query = f"'{folder_id}' in parents and name='{file_name}' and trashed=false"
    response = service.files().list(q=query, fields="files(id, webViewLink)").execute()
    files = response.get("files", [])

    if files:
        # If file exists, update it instead of re-uploading
        existing_file_id = files[0]["id"]
        media = MediaFileUpload(file_path, mimetype="text/plain", resumable=True)

        updated_file = service.files().update(
            fileId=existing_file_id,
            media_body=media
        ).execute()

        # Ensure the file has public sharing permissions
        service.permissions().create(
            fileId=existing_file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()

        # Fetch the updated sharing link
        file_info = service.files().get(fileId=existing_file_id, fields="webViewLink").execute()
        return file_info.get("webViewLink")

    else:
        # If file does not exist, upload a new one
        file_metadata = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(file_path, mimetype="text/plain")

        new_file = service.files().create(
            body=file_metadata, media_body=media, fields="id, webViewLink"
        ).execute()

        # Ensure the new file has public sharing permissions
        service.permissions().create(
            fileId=new_file["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()

        return new_file.get("webViewLink") # Return the file sharing link

def send_transcript_email(student_number, recipient_email, transcript_link):
    """
    Sends the interview transcript to the student and additional recipient.
    """
    smtp_server = "smtp.gmail.com"  # Replace with your SMTP server
    smtp_port = 587  # Port for TLS
    sender_email = "businessinternship.liacs@gmail.com"  # Your email
    sender_password = st.secrets["EMAIL_PASSWORD"]  # Store password securely
    student_email = f"{student_number}@vuw.leidenuniv.nl"

    # Create email message
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = student_email  # Primary recipient
    msg["Cc"] = recipient_email  # Additional recipient
    msg["Subject"] = "Your Interview Transcript from Leiden University"

    body = f"""
    Dear Student,

    Thank you for participating in the interview. Your transcript has been saved.

    You can download your transcript here:
    {transcript_link}

    Best regards,  
    Leiden University Interview System
    """

    msg.attach(MIMEText(body, "plain"))

    try:
        # Connect to SMTP server
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Secure connection
        server.login(sender_email, sender_password)

        # Send email to both recipients
        recipients = [student_email, recipient_email]
        server.sendmail(sender_email, recipients, msg.as_string())

        server.quit()
        print(f"Email sent to {recipients}")
    except Exception as e:
        print(f"Error sending email: {e}")