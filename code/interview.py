import streamlit as st
import time
from utils import (
    save_interview_data,
    send_transcript_email,
)
from database import ( save_interview_to_sheet, update_progress_sheet)
import os
import html  # For sanitizing query parameters
import uuid
import re
import importlib.util

folder_id = "123xBZ2YDy8BZrbErQb0U9TpGY-j3NdK7"  # Set the folder ID for the Google Drive folder where the interview data will be saved

# Load API library
provider = st.secrets.get("API_PROVIDER", "openai").lower()  # defaults to "openai" if not provided
model = st.secrets.get("MODEL", "gpt-3.5-turbo")

if provider == "openai" or "gpt" in model.lower():
    api = "openai"
    from openai import OpenAI
elif provider == "anthropic" or "claude" in model.lower():
    api = "anthropic"
    import anthropic
elif provider == "deepinfra":
    api = "deepinfra"
    import deepinfra  # Adjust the import as needed for your deepinfra client
else:
    raise ValueError(
        "API provider not recognized. Please set API_PROVIDER in st.secrets to 'openai', 'anthropic', or 'deepinfra'."
    )

# Assume you set an environment variable in st.secrets, e.g. "ENV": "test" or "production"
ENV = st.secrets.get("ENV", "production")  # default to production if not set
safe_mode = st.secrets.get("SAFE_MODE", "production")

# Extract query parameters early
query_params = st.query_params

# Load the appropriate configuration module dynamically:
if "interview_config" not in query_params:
    # In test mode or if no interview_config is provided, use the default config.py
    import config
    config_name = "Default"
else:
    # Get the interview config name from the query parameters (e.g., ?interview_config=techInterview)
    config_name = st.query_params.get("interview_config", ["Default"])
    # Build the path to the config file inside the "Interview_Configs" folder
    config_path = os.path.join(os.path.dirname(__file__), "interview_configs", f"{config_name}.py")
    if not os.path.exists(config_path):
        st.error(f"Configuration file {config_name}.py not found in interview_configs folder.")
        st.stop()
    spec = importlib.util.spec_from_file_location("config", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

# Set page title and icon
st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

# Define required parameters
required_params = ["student_number", "name", "company", "recipient_email"]

# Default values taken from the provided URL
default_values = {
    "student_number": "zohrehvanda",
    "name": "Miros",
    "company": "LIACS",
    "recipient_email": "j.s.deweert@gmail.com"
}

def validate_query_params(params, required_keys):
    missing_keys = []
    # If in test mode, fill in missing keys with default values; in production, mark them as missing.
    for key in required_keys:
        if key not in params or not params[key]:
            if ENV == "test":
                params[key] = default_values.get(key)
            else:
                missing_keys.append(key)
    
    # In test mode, additionally validate the email format
    if ENV == "test":
        email = params.get("recipient_email", "")
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            missing_keys.append("recipient_email (invalid format)")
    
    if missing_keys:
        return False, missing_keys
    return True, []

# Validate parameters
is_valid, missing_params = validate_query_params(query_params, required_params)

# In production, display an error if required parameters are missing
if not is_valid:
    st.error(f"Missing or invalid required parameter(s): {', '.join(missing_params)}")
    st.stop()

# Optionally, you might disable email sending if a certain setting is toggled in your config
if st.secrets.get("DISABLE_EMAIL", False):
    st.write("Email sending is disabled.")

# Extract respondent's name
respondent_name = html.unescape(query_params["name"])
recipient_email = html.unescape(query_params["recipient_email"])

# Check if session ID exists in session state, if not, create one
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Display parameters in sidebar
st.sidebar.title("Interview Details")
for param in required_params:
    # Fetch the first value of the list returned for each parameter and sanitize it
    sanitized_value = html.unescape(query_params[param])
    st.sidebar.write(f"{param.replace('_', ' ').capitalize()}: {sanitized_value}")

st.sidebar.write(f"Session ID: {st.session_state.session_id}")
st.sidebar.write(f"Interview Type: {config_name}")

# Initialise session state
if "interview_active" not in st.session_state:
    st.session_state.interview_active = True

if "messages" not in st.session_state:
    st.session_state.messages = []

if "email_sent" not in st.session_state:
    st.session_state.email_sent = False

# Store start time in session state
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime(
        "%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time)
    )

# URL to Qualtrics evaluation
evaluation_url = "https://leidenuniv.eu.qualtrics.com/jfe/form/SV_bvafC8YWGQJC1Ey"
evaluation_url_with_session = f"{evaluation_url}?session_id={st.session_state.session_id}"

# Add 'Quit' button to dashboard
col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and st.button("Quit", help="End the interview."):
        st.session_state.interview_active = False
        quit_message = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_message})

        # Save and upload interview data and get both link and file path
        transcript_link, transcript_file = save_interview_data(
            folder_id=folder_id,
            student_number=query_params["student_number"],
            company_name=query_params["company"]
        )
        st.session_state.transcript_link = transcript_link
        st.session_state.transcript_file = transcript_file

        # Send email with attachment (only once)
        send_transcript_email(
            query_params["student_number"],
            query_params["recipient_email"],
            transcript_link,
            transcript_file
        )
        st.session_state.email_sent = True

# After the interview ends
if not st.session_state.interview_active:
    st.empty()
    
    # Ensure transcript is saved and stored in session_state if not already done
    if "transcript_link" not in st.session_state or not st.session_state.transcript_link:
        transcript_link, transcript_file = save_interview_data(
            folder_id=folder_id,
            student_number=query_params["student_number"],
            company_name=query_params["company"]
        )
        st.session_state.transcript_link = transcript_link
        st.session_state.transcript_file = transcript_file
    
    # Send the email only if it hasn't been sent yet
    if not st.session_state.email_sent:
        send_transcript_email(
            query_params["student_number"],
            query_params["recipient_email"],
            st.session_state.transcript_link,
            st.session_state.transcript_file
        )
        st.session_state.email_sent = True
    
    st.markdown(f"""
    ### Your interview transcript has been saved and shared:
    [Click here to access the transcript]({st.session_state.transcript_link})
    """)
    
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
            <a href="{evaluation_url_with_session}" target="_blank" style="text-decoration: none; background-color: #4CAF50; color: white; padding: 15px 32px; text-align: center; font-size: 16px; border-radius: 8px;">Click here to evaluate the interview</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    # Saving the interview to Google Sheets
    duration_minutes = (time.time() - st.session_state.start_time) / 60
    interview_id = st.session_state.session_id
    student_id = query_params["student_number"]
    name = query_params["name"]
    company = query_params["company"]
    interview_type = config_name
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    transcript = ""
    for msg in st.session_state.messages:
        if msg["role"] in ["user", "assistant"]:
            transcript += f"{msg['role']}: {msg['content']}\n"
    
    save_interview_to_sheet(
        interview_id,
        student_id,
        name,
        company,
        interview_type,
        timestamp,
        transcript,
        f"{duration_minutes:.2f}"
    )
    
    update_progress_sheet(
        student_id,
        name,
        interview_type,
        timestamp  # current completion date
    )

# Upon rerun, display the previous conversation (except system prompt or first message)
for message in st.session_state.messages[1:]:
    if message["role"] == "assistant":
        avatar = config.AVATAR_INTERVIEWER
    else:
        avatar = config.AVATAR_RESPONDENT
    if not any(code in message["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

# Load API client
if api == "openai":
    client = OpenAI(api_key=st.secrets["API_KEY"])
    api_kwargs = {"stream": True}
elif api == "anthropic":
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    api_kwargs = {"system": st.secrets.get("SYSTEM_PROMPT", "Your default system prompt")}
elif api == "deepinfra":
    client = deepinfra.Client(api_key=st.secrets["DEEPINFRA_API_KEY"])
    api_kwargs = {"stream": True}
    
api_kwargs["messages"] = st.session_state.messages
api_kwargs["model"] = model
api_kwargs["max_tokens"] = config.MAX_OUTPUT_TOKENS
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

if config_name.lower() == "end_reflection_interview":
    from database import get_transcript_by_student_and_type
    midterm_transcript = get_transcript_by_student_and_type(query_params["student_number"], "midterm_interview")
    try:
        if midterm_transcript:
            context_message = (
                "Midterm Interview Transcript (provided as context for the End Reflection Interview):\n\n"
                f"{midterm_transcript}"
            )
    except:
        midterm_transcript = None

if not st.session_state.messages:
    if api == "openai":
        if config_name.lower() == "end_reflection_interview" and midterm_transcript:
            system_prompt = (
                "Midterm Interview Transcript (provided as context for the End Reflection Interview):\n\n"
                f"{midterm_transcript}\n\n"
                f"{config.INTERVIEW_OUTLINE}"
            )
        else:
            system_prompt = config.INTERVIEW_OUTLINE

        st.session_state.messages.append(
            {"role": "system", "content": system_prompt}
        )
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            stream = client.chat.completions.create(**api_kwargs)
            message_interviewer = st.write_stream(stream)
    elif api == "anthropic":
        st.session_state.messages.append({"role": "user", "content": "Hi"})
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            message_interviewer = ""
            with client.messages.stream(**api_kwargs) as stream:
                for text_delta in stream.text_stream:
                    if text_delta is not None:
                        message_interviewer += text_delta
                    message_placeholder.markdown(message_interviewer + "▌")
            message_placeholder.markdown(message_interviewer)
    st.session_state.messages.append(
        {"role": "assistant", "content": message_interviewer}
    )
    save_interview_data(
        folder_id=folder_id,
        student_number=query_params["student_number"],
        company_name=query_params["company"]
    )

if st.session_state.interview_active:
    if message_respondent := st.chat_input("Your message here"):
        st.session_state.messages.append(
            {"role": "user", "content": message_respondent}
        )
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(message_respondent)
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            message_interviewer = ""
            if api == "openai":
                stream = client.chat.completions.create(**api_kwargs)
                for message in stream:
                    text_delta = message.choices[0].delta.content
                    if text_delta is not None:
                        message_interviewer += text_delta
                    if len(message_interviewer) > 5:
                        message_placeholder.markdown(message_interviewer + "▌")
                    if any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                        message_placeholder.empty()
                        break
            elif api == "anthropic":
                with client.messages.stream(**api_kwargs) as stream:
                    for text_delta in stream.text_stream:
                        if text_delta is not None:
                            message_interviewer += text_delta
                        if len(message_interviewer) > 5:
                            message_placeholder.markdown(message_interviewer + "▌")
                        if any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                            message_placeholder.empty()
                            break
            if not any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                message_placeholder.markdown(message_interviewer)
                st.session_state.messages.append(
                    {"role": "assistant", "content": message_interviewer}
                )
                try:
                    transcript_link, transcript_file = save_interview_data(
                        folder_id=folder_id,
                        student_number=query_params["student_number"],
                        company_name=query_params["company"]
                    )
                except:
                    pass
            for code in config.CLOSING_MESSAGES.keys():
                if code in message_interviewer:
                    st.session_state.messages.append(
                        {"role": "assistant", "content": message_interviewer}
                    )
                    st.session_state.interview_active = False
                    closing_message = config.CLOSING_MESSAGES[code]
                    st.markdown(closing_message)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": closing_message}
                    )
                    time.sleep(5)
                    st.rerun()
