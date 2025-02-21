import streamlit as st
import time
from utils import (
    check_password,
    check_if_interview_completed,
    save_interview_data,
    send_transcript_email,
)
import os
import config
import html  # For sanitizing query parameters
import uuid

# Load API library
if "gpt" in config.MODEL.lower():
    api = "openai"
    from openai import OpenAI

elif "claude" in config.MODEL.lower():
    api = "anthropic"
    import anthropic
else:
    raise ValueError(
        "Model does not contain 'gpt' or 'claude'; unable to determine API."
    )

# Set page title and icon
st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

# Function to validate query parameters
def validate_query_params(params, required_keys):
    # TODO: if doesn't exist, add on a default item. 
    # in config, let's session type. if production, then these keys are not needed. 
    # #If in test, let's check if the email address makes sense. 
    #  TODO: option, disable email sending. 
    missing_keys = [key for key in required_keys if key not in params or not params[key]]
    if missing_keys:
        return False, missing_keys
    return True, []

# Extract query parameters
query_params = st.query_params

# Define required parameters
required_params = ["student_number", "name", "company", "recipient_email"]

# Validate parameters
is_valid, missing_params = validate_query_params(query_params, required_params)

# Display error and stop if parameters are missing
if not is_valid:
    st.error(f"Missing required parameter(s): {', '.join(missing_params)}")
    st.stop()

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

# Check if usernames and logins are enabled
if config.LOGINS:
    # Check password (displays login screen)
    pwd_correct, username = check_password()
    if not pwd_correct:
        st.stop()
    else:
        st.session_state.username = username
else:
    st.session_state.username = "testaccount"

# Create directories if they do not already exist
if not os.path.exists(config.TRANSCRIPTS_DIRECTORY):
    os.makedirs(config.TRANSCRIPTS_DIRECTORY)
if not os.path.exists(config.TIMES_DIRECTORY):
    os.makedirs(config.TIMES_DIRECTORY)
if not os.path.exists(config.BACKUPS_DIRECTORY):
    os.makedirs(config.BACKUPS_DIRECTORY)

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

# Check if interview previously completed
interview_previously_completed = check_if_interview_completed(
    config.TIMES_DIRECTORY, st.session_state.username
)

# If app started but interview was previously completed
if interview_previously_completed and not st.session_state.messages:

    st.session_state.interview_active = False
    completed_message = "Interview already completed."
    st.markdown(completed_message)
    
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
        transcript_link = save_interview_data(
            username=st.session_state.username,
            transcripts_directory=config.TRANSCRIPTS_DIRECTORY,
            times_directory=config.TIMES_DIRECTORY,
            folder_id="123xBZ2YDy8BZrbErQb0U9TpGY-j3NdK7",
            student_number=query_params["student_number"],
            company_name=query_params["company"])
        
        # Send email transscript
        send_transcript_email(query_params["student_number"], query_params["recipient_email"], transcript_link)
        
# After the interview ends
if not st.session_state.interview_active:
    # Clear the screen
    st.empty()
    
    # Ensure transcript is saved before showing the link (When the interview ended natuarlly)
    if "transcript_link" not in st.session_state or not st.session_state.transcript_link:
        st.session_state.transcript_link = save_interview_data(
            username=st.session_state.username,
            transcripts_directory=config.TRANSCRIPTS_DIRECTORY,
            times_directory=config.TIMES_DIRECTORY,
            folder_id="123xBZ2YDy8BZrbErQb0U9TpGY-j3NdK7",
            student_number=query_params["student_number"],
            company_name=query_params["company"]
        )
        # Send email transscript
        send_transcript_email(query_params["student_number"], query_params["recipient_email"], st.session_state.transcript_link)
    
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
    client = anthropic.Anthropic(api_key=st.secrets["API_KEY"])
    api_kwargs = {"system": config.SYSTEM_PROMPT}

# API kwargs
api_kwargs["messages"] = st.session_state.messages
api_kwargs["model"] = config.MODEL
api_kwargs["max_tokens"] = config.MAX_OUTPUT_TOKENS
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

# In case the interview history is still empty, pass system prompt to model, and
# generate and display its first message
if not st.session_state.messages:
    
    if api == "openai":

        st.session_state.messages.append(
            {"role": "system", "content": config.INTERVIEW_OUTLINE}
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
            username=st.session_state.username,
            transcripts_directory=config.TRANSCRIPTS_DIRECTORY,
            times_directory=config.TIMES_DIRECTORY,
            folder_id="123xBZ2YDy8BZrbErQb0U9TpGY-j3NdK7",
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

                
                
                # Commented out as it does not overwrite old file and create duplicates
                
                # # Regularly store interview progress as backup, but prevent script from
                # # stopping in case of a write error
                try:

                    transcript_link = save_interview_data(
                    username=st.session_state.username,
                    transcripts_directory=config.TRANSCRIPTS_DIRECTORY,
                    times_directory=config.TIMES_DIRECTORY,
                    folder_id="123xBZ2YDy8BZrbErQb0U9TpGY-j3NdK7",
                    student_number=query_params["student_number"],
                    company_name=query_params["company"] )

                except:

                    pass
                # It saves the interview data every 5 seconds, that is redundant

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


                    # # Store final transcript and time
                    # final_transcript_stored = False
                    # transcript_link = None  # Initialize the variable

                    # transcript_link = save_interview_data(
                    #         username=st.session_state.username,
                    #         transcripts_directory=config.TRANSCRIPTS_DIRECTORY,
                    #         times_directory=config.TIMES_DIRECTORY,
                    #         folder_id="123xBZ2YDy8BZrbErQb0U9TpGY-j3NdK7",  # Ensure correct folder ID
                    #         student_number=query_params["student_number"],
                    #         company_name=query_params["company"]
                    #     )

                    # final_transcript_stored = check_if_interview_completed(
                    #         config.TRANSCRIPTS_DIRECTORY, st.session_state.username
                    #     )
                    # time.sleep(0.1)
                    #
                    
