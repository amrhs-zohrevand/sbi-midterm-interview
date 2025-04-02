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

# Initialise messages list in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Store start time in session state
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime(
        "%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time)
    )

# URL to Qualtrics evaluation
evaluation_url = "https://leidenuniv.eu.qualtrics.com/jfe/form/SV_bvafC8YWGQJC1Ey"

# Append session ID as query parameter
evaluation_url_with_session = f"{evaluation_url}?session_id={st.session_state.session_id}"

# Add 'Quit' button to dashboard
col1, col2 = st.columns([0.85, 0.15])
# Place where the second column is
with col2:

    # If interview is active and 'Quit' button is clicked
    if st.session_state.interview_active and st.button("Quit", help="End the interview."):
        st.session_state.interview_active = False
        quit_message = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_message})

        # Save and upload interview data
        transcript_link, transcript_file = save_interview_data(
        folder_id=folder_id,
        student_number=query_params["student_number"],
        company_name=query_params["company"]
    )
    send_transcript_email(query_params["student_number"], query_params["recipient_email"], transcript_link, transcript_file)

        
# After the interview ends
if not st.session_state.interview_active:
    # Clear the screen
    st.empty()
    
    # Ensure transcript is saved before showing the link (When the interview ended natuarlly)
    if "transcript_link" not in st.session_state or not st.session_state.transcript_link:
        st.session_state.transcript_link, st.session_state.transcript_file = save_interview_data(
    folder_id=folder_id,
    student_number=query_params["student_number"],
    company_name=query_params["company"]
    )
    send_transcript_email(query_params["student_number"], query_params["recipient_email"], transcript_link, transcript_file)
    
    # Center the button on the page
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
    # Calculate the interview duration (in minutes)
    duration_minutes = (time.time() - st.session_state.start_time) / 60

    # Set values for the record
    interview_id = st.session_state.session_id  # Use the session ID as Interview ID
    student_id = query_params["student_number"]
    name = query_params["name"]
    company = query_params["company"]
    
    # Set the interview type (modify as needed)
    interview_type = config_name
    
    # Get the current timestamp
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    # Build the transcript from the conversation
    transcript = ""
    for msg in st.session_state.messages:
        if msg["role"] in ["user", "assistant"]:
            transcript += f"{msg['role']}: {msg['content']}\n"
    
    # Call the function to save the record to the Google Sheets database
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
    # Only display messages without codes
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
    # Adjust these kwargs based on deepinfra's API requirements:
    api_kwargs = {"stream": True}
    

# API kwargs
api_kwargs["messages"] = st.session_state.messages
api_kwargs["model"] = model
api_kwargs["max_tokens"] = config.MAX_OUTPUT_TOKENS
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

# In case the interview history is still empty, pass system prompt to model, and
# generate and display its first message

# Check if the current interview is an end reflection interview and if a midterm transcript exists
if config_name.lower() == "end_reflection_interview":
    from database import get_transcript_by_student_and_type
    midterm_transcript = get_transcript_by_student_and_type(query_params["student_number"], "midterm_interview")
    try:
        if midterm_transcript:
            # Insert a system message at the beginning with the midterm transcript as context.
            context_message = (
                "Midterm Interview Transcript (provided as context for the End Reflection Interview):\n\n"
                f"{midterm_transcript}"
            )
    except:
        midterm_transcript = None



if not st.session_state.messages:
    
    if api == "openai":
        
    # Prepare the system prompt by including the midterm transcript if available.
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
                    if text_delta != None:
                        message_interviewer += text_delta
                    message_placeholder.markdown(message_interviewer + "▌")
            message_placeholder.markdown(message_interviewer)

    st.session_state.messages.append(
        {"role": "assistant", "content": message_interviewer}
    )
    
    # Commented out as it does not overwrite old file and create duplicates

    # Store first backup files to record who started the interview
    save_interview_data(
            folder_id=folder_id,
            student_number=query_params["student_number"],
            company_name=query_params["company"] )

# Main chat if interview is active
if st.session_state.interview_active:

    # Chat input and message for respondent
    if message_respondent := st.chat_input("Your message here"):
        st.session_state.messages.append(
            {"role": "user", "content": message_respondent}
        )

        # Display respondent message
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(message_respondent)

        # Generate and display interviewer message
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):

            # Create placeholder for message in chat interface
            message_placeholder = st.empty()

            # Initialise message of interviewer
            message_interviewer = ""

            if api == "openai":

                # Stream responses
                stream = client.chat.completions.create(**api_kwargs)

                for message in stream:
                    text_delta = message.choices[0].delta.content
                    if text_delta != None:
                        message_interviewer += text_delta
                    # Start displaying message only after 5 characters to first check for codes
                    if len(message_interviewer) > 5:
                        message_placeholder.markdown(message_interviewer + "▌")
                    if any(
                        code in message_interviewer
                        for code in config.CLOSING_MESSAGES.keys()
                    ):
                        # Stop displaying the progress of the message in case of a code
                        message_placeholder.empty()
                        break

            elif api == "anthropic":

                # Stream responses
                with client.messages.stream(**api_kwargs) as stream:
                    for text_delta in stream.text_stream:
                        if text_delta != None:
                            message_interviewer += text_delta
                        # Start displaying message only after 5 characters to first check for codes
                        if len(message_interviewer) > 5:
                            message_placeholder.markdown(message_interviewer + "▌")
                        if any(
                            code in message_interviewer
                            for code in config.CLOSING_MESSAGES.keys()
                        ):
                            # Stop displaying the progress of the message in case of a code
                            message_placeholder.empty()
                            break

            # If no code is in the message, display and store the message
            if not any(
                code in message_interviewer for code in config.CLOSING_MESSAGES.keys()
            ):

                message_placeholder.markdown(message_interviewer)
                st.session_state.messages.append(
                    {"role": "assistant", "content": message_interviewer}
                )

                try:

                    transcript_link = save_interview_data(
                    folder_id=folder_id,
                    student_number=query_params["student_number"],
                    company_name=query_params["company"] )

                except:

                    pass


            # If code in the message, display the associated closing message instead
            # Loop over all codes
            for code in config.CLOSING_MESSAGES.keys():
                if code in message_interviewer:
                    # Store message in list of messages
                    st.session_state.messages.append(
                        {"role": "assistant", "content": message_interviewer}
                    )

                    # Set chat to inactive and display closing message
                    st.session_state.interview_active = False
                    closing_message = config.CLOSING_MESSAGES[code]
                    st.markdown(closing_message)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": closing_message}
                    )
                    
                    # Delay for 5 seconds before rerunning
                    time.sleep(5)
                    st.rerun()