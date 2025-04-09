import streamlit as st
import time
from utils import save_interview_data, send_transcript_email
from database import save_interview_to_sheet, update_progress_sheet, update_interview_summary
from interview_selection import get_context_transcript
import os
import html
import uuid
import re
import importlib.util

# API client setup (unchanged)
provider = st.secrets.get("API_PROVIDER", "openai").lower()
model = st.secrets.get("MODEL", "gpt-3.5-turbo")
if provider == "openai" or "gpt" in model.lower():
    api = "openai"
    from openai import OpenAI
elif provider == "anthropic" or "claude" in model.lower():
    api = "anthropic"
    import anthropic
elif provider == "deepinfra":
    api = "deepinfra"
    import deepinfra
else:
    raise ValueError("Unrecognized API provider.")

if api == "openai":
    client = OpenAI(api_key=st.secrets["API_KEY"])
elif api == "anthropic":
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
elif api == "deepinfra":
    client = deepinfra.Client(api_key=st.secrets["DEEPINFRA_API_KEY"])

ENV = st.secrets.get("ENV", "production")
query_params = st.query_params
if "interview_config" not in query_params:
    import config
    config_name = "Default"
else:
    config_name = st.query_params.get("interview_config", ["Default"])
    config_path = os.path.join(os.path.dirname(__file__), "interview_configs", f"{config_name}.py")
    if not os.path.exists(config_path):
        st.error(f"Configuration file {config_name}.py not found.")
        st.stop()
    spec = importlib.util.spec_from_file_location("config", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

st.set_page_config(page_title="Interview", page_icon=config.AVATAR_INTERVIEWER)

required_params = ["student_number", "name", "company", "recipient_email"]
def validate_query_params(params):
    missing = []
    for key in required_params:
        if key not in params or not params[key]:
            missing.append(key)
    if missing:
        return False, missing
    return True, []

is_valid, missing = validate_query_params(query_params)
if not is_valid:
    st.error(f"Missing parameters: {', '.join(missing)}")
    st.stop()

respondent_name = html.unescape(query_params["name"])
recipient_email = html.unescape(query_params["recipient_email"])

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "interview_active" not in st.session_state:
    st.session_state.interview_active = True
if "messages" not in st.session_state:
    st.session_state.messages = []
if "email_sent" not in st.session_state:
    st.session_state.email_sent = False
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()

if "awaiting_email_confirmation" not in st.session_state:
    st.session_state.awaiting_email_confirmation = False

# Sidebar with interview details
st.sidebar.title("Interview Details")
for param in required_params:
    sanitized_value = html.unescape(query_params[param])
    st.sidebar.write(f"{param.replace('_', ' ').capitalize()}: {sanitized_value}")
st.sidebar.write(f"Session ID: {st.session_state.session_id}")
st.sidebar.write(f"Interview Type: {config_name}")

# Evaluation URL definition
evaluation_url = "https://leidenuniv.eu.qualtrics.com/jfe/form/SV_bvafC8YWGQJC1Ey"
evaluation_url_with_session = f"{evaluation_url}?session_id={st.session_state.session_id}"

col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and not st.session_state.awaiting_email_confirmation:
        if st.button("Quit"):
            st.session_state.awaiting_email_confirmation = True

if st.session_state.awaiting_email_confirmation:
    st.subheader("Confirm Email Before Ending Interview")
    email_input = st.text_input("Confirm or update your email address:", value=recipient_email)
    send_email = st.checkbox("Yes, send a transcript to this email.")
    if st.button("Confirm and Quit"):
        st.session_state.interview_active = False
        st.session_state.awaiting_email_confirmation = False
        st.session_state.email_confirmed = True
        quit_message = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_message})

        transcript_link, transcript_file = save_interview_data(
            student_number=query_params["student_number"],
            company_name=query_params["company"]
        )
        st.session_state.transcript_link = transcript_link
        st.session_state.transcript_file = transcript_file

        if send_email:
            send_transcript_email(
                student_number=query_params["student_number"],
                recipient_email=email_input,
                transcript_link=transcript_link,
                transcript_file=transcript_file,
                name_from_form=query_params["name"]
            )
            st.session_state.email_sent = True

        st.markdown("### Your interview transcript has been saved.")
        if send_email:
            st.markdown("A copy has been emailed to you.")

        st.markdown(
            f"""
            <div style="display: flex; justify-content: center; align-items: center; margin-top: 2em;">
                <a href="{evaluation_url_with_session}" target="_blank" style="text-decoration: none; background-color: #4CAF50; color: white; padding: 15px 32px; text-align: center; font-size: 16px; border-radius: 8px;">Click here to evaluate the interview</a>
            </div>
            """,
            unsafe_allow_html=True,
        )


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
        student_number=query_params["student_number"],
        recipient_email=query_params["recipient_email"],
        transcript_link=transcript_link,
        transcript_file=transcript_file,
        name_from_form=query_params["name"]  # NEW
    )
        st.session_state.email_sent = True
    
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
    
    # --- NEW: Generate and store summary via the LLM ---
    summary_prompt = (
        "Please provide a concise but detailed summary for the following interview transcript:\n\n" 
        + transcript
    )
    if api == "openai":
        # Call the LLM without streaming to get the full summary response directly.
        summary_response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": summary_prompt}],
            max_tokens=200,
            temperature=0.7,
            stream=False
        )
        summary_text = summary_response.choices[0].message.content.strip()
    else:
        summary_text = "Summary generation not implemented for this provider."

    st.write("Generated Summary:", summary_text)  # Optional: display for debugging
    update_interview_summary(interview_id, summary_text)
    # --- End New Section ---

for message in st.session_state.messages[1:]:
    if message["role"] == "assistant":
        avatar = config.AVATAR_INTERVIEWER
    else:
        avatar = config.AVATAR_RESPONDENT
    if not any(code in message["content"] for code in config.CLOSING_MESSAGES.keys()):
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

# Remove redundant client reinitialization below; we already created the client above.
api_kwargs = {"stream": True}
if api == "anthropic":
    api_kwargs = {"system": st.secrets.get("SYSTEM_PROMPT", "Your default system prompt")}
    
api_kwargs["messages"] = st.session_state.messages
api_kwargs["model"] = model
api_kwargs["max_tokens"] = config.MAX_OUTPUT_TOKENS
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

if config_name != "Default":
    context_transcript = get_context_transcript(query_params["student_number"], config_name)
    if context_transcript:
        st.info("✅ Context summary loaded from previous interview.")
    else:
        st.warning("⚠️ No context summary available for this interview type.")

if not st.session_state.messages:
    if api == "openai":
        if context_transcript:
            system_prompt = (
                "Context Transcript Summary (provided as context for the Interview):\n\n"
                f"{context_transcript}\n\n"
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
