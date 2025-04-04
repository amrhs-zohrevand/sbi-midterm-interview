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

ENV = st.secrets.get("ENV", "production")
safe_mode = st.secrets.get("SAFE_MODE", "production")
query_params = st.query_params

if "interview_config" not in query_params:
    import config
    config_name = "Default"
else:
    config_name = st.query_params.get("interview_config", ["Default"])
    config_path = os.path.join(os.path.dirname(__file__), "interview_configs", f"{config_name}.py")
    if not os.path.exists(config_path):
        st.error(f"Configuration file {config_name}.py not found in interview_configs folder.")
        st.stop()
    spec = importlib.util.spec_from_file_location("config", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)
required_params = ["student_number", "name", "company", "recipient_email"]
default_values = {
    "student_number": "zohrehvanda",
    "name": "Miros",
    "company": "LIACS",
    "recipient_email": "j.s.deweert@gmail.com"
}

def validate_query_params(params, required_keys):
    missing_keys = []
    for key in required_keys:
        if key not in params or not params[key]:
            if ENV == "test":
                params[key] = default_values.get(key)
            else:
                missing_keys.append(key)
    
    if ENV == "test":
        email = params.get("recipient_email", "")
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            missing_keys.append("recipient_email (invalid format)")
    
    if missing_keys:
        return False, missing_keys
    return True, []

is_valid, missing_params = validate_query_params(query_params, required_params)
if not is_valid:
    st.error(f"Missing or invalid required parameter(s): {', '.join(missing_params)}")
    st.stop()

if st.secrets.get("DISABLE_EMAIL", False):
    st.write("Email sending is disabled.")

respondent_name = html.unescape(query_params["name"])
recipient_email = html.unescape(query_params["recipient_email"])

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

st.sidebar.title("Interview Details")
for param in required_params:
    sanitized_value = html.unescape(query_params[param])
    st.sidebar.write(f"{param.replace('_', ' ').capitalize()}: {sanitized_value}")

st.sidebar.write(f"Session ID: {st.session_state.session_id}")
st.sidebar.write(f"Interview Type: {config_name}")

if "interview_active" not in st.session_state:
    st.session_state.interview_active = True

if "messages" not in st.session_state:
    st.session_state.messages = []

if "email_sent" not in st.session_state:
    st.session_state.email_sent = False

if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
    st.session_state.start_time_file_names = time.strftime(
        "%Y_%m_%d_%H_%M_%S", time.localtime(st.session_state.start_time)
    )

evaluation_url = "https://leidenuniv.eu.qualtrics.com/jfe/form/SV_bvafC8YWGQJC1Ey"
evaluation_url_with_session = f"{evaluation_url}?session_id={st.session_state.session_id}"

col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and st.button("Quit", help="End the interview."):
        st.session_state.interview_active = False
        quit_message = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_message})

        transcript_link, transcript_file = save_interview_data(
            student_number=query_params["student_number"],
            company_name=query_params["company"]
        )
        st.session_state.transcript_link = transcript_link
        st.session_state.transcript_file = transcript_file

        send_transcript_email(
            query_params["student_number"],
            query_params["recipient_email"],
            transcript_link,
            transcript_file
        )
        st.session_state.email_sent = True

if not st.session_state.interview_active:
    st.empty()
    
    if "transcript_link" not in st.session_state or not st.session_state.transcript_link:
        transcript_link, transcript_file = save_interview_data(
            student_number=query_params["student_number"],
            company_name=query_params["company"]
        )
        st.session_state.transcript_link = transcript_link
        st.session_state.transcript_file = transcript_file
    
    if not st.session_state.email_sent:
        send_transcript_email(
            query_params["student_number"],
            query_params["recipient_email"],
            st.session_state.transcript_link,
            st.session_state.transcript_file
        )
        st.session_state.email_sent = True
    
    st.markdown("### Your interview transcript has been saved. Please check your email for the transcript attachment.")
    
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; align-items: center; height: 100vh;">
            <a href="{evaluation_url_with_session}" target="_blank" style="text-decoration: none; background-color: #4CAF50; color: white; padding: 15px 32px; text-align: center; font-size: 16px; border-radius: 8px;">Click here to evaluate the interview</a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
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
        timestamp
    )

for message in st.session_state.messages[1:]:
    if message["role"] == "assistant":
        avatar = config.AVATAR_INTERVIEWER
    else:
        avatar = config.AVATAR_RESPONDENT
    if not any(code in message["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

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
