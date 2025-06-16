import streamlit as st
import time
from utils import save_interview_data, send_transcript_email
from database import (
    save_interview_to_sheet,
    update_progress_sheet,
    update_interview_summary,
)
from interview_selection import get_context_transcript
import os
import html
import uuid
import importlib.util

# Voice input imports
import tempfile
from streamlit_mic_recorder import mic_recorder

# ----------------------------------------------------------------------------
# API client setup
# ----------------------------------------------------------------------------
provider = st.secrets.get("API_PROVIDER", "openai").lower()
model = st.secrets.get("MODEL", "gpt-3.5-turbo")

from openai import OpenAI

if provider == "openai":
    api = "openai"
    client = OpenAI(api_key=st.secrets["API_KEY"])

elif provider == "deepinfra":
    api = "openai"
    client = OpenAI(
        api_key=st.secrets["DEEPINFRA_API_KEY"],
        base_url="https://api.deepinfra.com/v1/openai",
    )

elif provider == "anthropic" or "claude" in model.lower():
    api = "anthropic"
    import anthropic  # noqa: E402

    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
else:
    raise ValueError(
        "Unrecognized API provider – supported: openai, deepinfra, anthropic."
    )

# ----------------------------------------------------------------------------
# Setup OpenAI client for audio transcription (Whisper)
# ----------------------------------------------------------------------------
audio_client = OpenAI(api_key=st.secrets["API_KEY"])

def transcribe(audio_bytes: bytes) -> str:
    # write bytes to a temp wav
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    # call Whisper
    with open(tmp_path, "rb") as f:
        resp = audio_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text"
        )
    # resp may be a str (when response_format="text"), an object with .text, or a dict
    if hasattr(resp, "text"):
        text = resp.text
    elif isinstance(resp, dict) and "text" in resp:
        text = resp["text"]
    else:
        text = resp  # assume it's already a str
    return text.strip()

# ----------------------------------------------------------------------------
# Configuration loading
# ----------------------------------------------------------------------------
ENV = st.secrets.get("ENV", "production")
query_params = st.query_params
if "interview_config" not in query_params:
    import config  # local default

    config_name = "Default"
else:
    config_name = st.query_params.get("interview_config", ["Default"])
    config_path = os.path.join(
        os.path.dirname(__file__), "interview_configs", f"{config_name}.py"
    )
    if not os.path.exists(config_path):
        st.error(f"Configuration file {config_name}.py not found.")
        st.stop()
    spec = importlib.util.spec_from_file_location("config", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)

# ----------------------------------------------------------------------------
# Helper to fetch query-string parameters safely
# ----------------------------------------------------------------------------
def _get_param(name: str, default: str = "") -> str:
    """Return the query-string parameter as a string or *default* if missing."""
    val = query_params.get(name, default)
    if isinstance(val, list):
        val = val[0]
    return html.unescape(val)

# ----------------------------------------------------------------------------
# Streamlit session-state defaults
# ----------------------------------------------------------------------------
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
if "show_evaluation_only" not in st.session_state:
    st.session_state.show_evaluation_only = False

# ----------------------------------------------------------------------------
# "student_number" **and "company"** are now optional – only the fields below are required.
# ----------------------------------------------------------------------------
required_params = ["name", "recipient_email"]

def validate_query_params(params):
    missing = [k for k in required_params if k not in params or not params[k]]
    return len(missing) == 0, missing

is_valid, missing = validate_query_params(query_params)
if not is_valid:
    st.error(f"Missing parameters: {', '.join(missing)}")
    st.stop()

# Fetch parameters -----------------------------------------------------------
student_number = _get_param("student_number", "")
respondent_name = _get_param("name")
recipient_email = _get_param("recipient_email")
company_name = _get_param("company")

# ----------------------------------------------------------------------------
# Qualtrics post-interview survey link (CONFIG-DRIVEN)
# ----------------------------------------------------------------------------
DEFAULT_QUALTRICS_URL = (
    "https://leidenuniv.eu.qualtrics.com/jfe/form/SV_bvafC8YWGQJC1Ey"
)
evaluation_url = getattr(
    config, "POST_INTERVIEW_SURVEY_URL", DEFAULT_QUALTRICS_URL
)
evaluation_url_with_session = (
    f"{evaluation_url}?session_id={st.session_state.session_id}"
)

# ----------------------------------------------------------------------------
# EARLY EXIT if the only thing left to show is the evaluation button
# ----------------------------------------------------------------------------
if st.session_state.show_evaluation_only:
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center; align-items: center; margin-top: 2em;">
            <a href="{evaluation_url_with_session}" target="_blank"
               style="text-decoration: none; background-color: #4CAF50; color: white;
                      padding: 15px 32px; text-align: center; font-size: 16px;
                      border-radius: 8px;">
               Click here to evaluate the interview
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# ----------------------------------------------------------------------------
# Sidebar with interview details – hide student number and company when absent
# ----------------------------------------------------------------------------
st.sidebar.title("Interview Details")
for param in required_params:
    st.sidebar.write(
        f"{param.replace('_', ' ').capitalize()}: {html.unescape(query_params[param])}"
    )
if company_name:
    st.sidebar.write(f"Company: {company_name}")
if student_number:
    st.sidebar.write(f"Student number: {student_number}")
st.sidebar.write(f"Session ID: {st.session_state.session_id}")

# ----------------------------------------------------------------------------
# Top banner with Quit button
# ----------------------------------------------------------------------------
col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and not st.session_state.awaiting_email_confirmation:
        if st.button("Quit"):
            st.session_state.awaiting_email_confirmation = True

# ----------------------------------------------------------------------------
# Quit & Completion flow – confirm email & save transcript
# ----------------------------------------------------------------------------
if st.session_state.awaiting_email_confirmation:
    st.subheader("Confirm Email Before Ending Interview")
    email_input = st.text_input(
        "Confirm or update your email address:", value=recipient_email
    )
    send_email = st.checkbox("Yes, send a transcript to this email.")
    if st.button("Confirm and Quit"):
        # ... existing quit logic unchanged ...
        st.session_state.interview_active = False
        st.session_state.awaiting_email_confirmation = False
        st.session_state.email_confirmed = True
        quit_msg = "You have cancelled the interview."
        st.session_state.messages.append({"role": "assistant", "content": quit_msg})
        transcript_link, transcript_file = save_interview_data(
            student_number=student_number,
            company_name=company_name,
        )
        st.session_state.transcript_link = transcript_link
        st.session_state.transcript_file = transcript_file
        if send_email:
            send_transcript_email(
                student_number=student_number,
                recipient_email=email_input,
                transcript_link=transcript_link,
                transcript_file=transcript_file,
                name_from_form=respondent_name,
            )
            st.session_state.email_sent = True
        duration_minutes = (time.time() - st.session_state.start_time) / 60
        interview_id = st.session_state.session_id
        student_id = student_number
        name = respondent_name
        company = company_name
        interview_type = config_name
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        transcript_text = "".join(
            f"{msg['role']}: {msg['content']}\n"
            for msg in st.session_state.messages
            if msg["role"] in ["user", "assistant"]
        )
        save_interview_to_sheet(
            interview_id,
            student_id,
            name,
            company,
            interview_type,
            timestamp,
            transcript_text,
            f"{duration_minutes:.2f}",
        )
        if student_number:
            update_progress_sheet(student_number, name, interview_type, timestamp)
        summary_prompt = (
            "Please provide a concise but detailed summary for the following interview transcript:\n\n"
            + transcript_text
        )
        if api == "openai":
            if provider == "deepinfra":
                summary_messages = [{"role": "user", "content": summary_prompt}]
            else:
                summary_messages = [{"role": "system", "content": summary_prompt}]
            summary_response = client.chat.completions.create(
                model=model,
                messages=summary_messages,
                max_tokens=200,
                temperature=0.7,
                stream=False,
            )
            summary_text = summary_response.choices[0].message.content.strip()
        else:
            summary_text = "Summary generation not implemented for this provider."
        update_interview_summary(interview_id, summary_text)
        st.session_state.show_evaluation_only = True
        st.rerun()

# ----------------------------------------------------------------------------
# Post-interview actions and persistence (automatic bot-closure path)
# ----------------------------------------------------------------------------
if not st.session_state.interview_active and not st.session_state.awaiting_email_confirmation:
    # ... existing post-interview logic unchanged ...
    # Save to sheet, update progress, generate summary
    duration_minutes = (time.time() - st.session_state.start_time) / 60
    interview_id = st.session_state.session_id
    student_id = student_number
    name = respondent_name
    company = company_name
    interview_type = config_name
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    transcript = "".join(
        f"{msg['role']}: {msg['content']}\n"
        for msg in st.session_state.messages
        if msg["role"] in ["user", "assistant"]
    )
    save_interview_to_sheet(
        interview_id,
        student_id,
        name,
        company,
        interview_type,
        timestamp,
        transcript,
        f"{duration_minutes:.2f}",
    )
    if student_number:
        update_progress_sheet(student_number, name, interview_type, timestamp)
    summary_prompt = (
        "Please provide a concise but detailed summary for the following interview transcript:\n\n"
        + transcript
    )
    if api == "openai":
        if provider == "deepinfra":
            summary_messages = [{"role": "user", "content": summary_prompt}]
        else:
            summary_messages = [{"role": "system", "content": summary_prompt}]
        summary_response = client.chat.completions.create(
            model=model,
            messages=summary_messages,
            max_tokens=200,
            temperature=0.7,
            stream=False,
        )
        summary_text = summary_response.choices[0].message.content.strip()
    else:
        summary_text = "Summary generation not implemented for this provider."
    update_interview_summary(interview_id, summary_text)
    st.session_state.show_evaluation_only = True
    st.rerun()

# ----------------------------------------------------------------------------
# Chat UI helpers – render prior conversation
# ----------------------------------------------------------------------------
for message in st.session_state.messages[1:]:
    avatar = (
        config.AVATAR_INTERVIEWER
        if message["role"] == "assistant"
        else config.AVATAR_RESPONDENT
    )
    if not any(
        code in message["content"] for code in config.CLOSING_MESSAGES.keys()
    ):
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

# ----------------------------------------------------------------------------
# Helper dict for LLM calls
# ----------------------------------------------------------------------------
api_kwargs = {"stream": True}
if api == "anthropic":
    api_kwargs["system"] = st.secrets.get(
        "SYSTEM_PROMPT", "Your default system prompt"
    )
api_kwargs.update(
    {
        "messages": st.session_state.messages,
        "model": model,
        "max_tokens": config.MAX_OUTPUT_TOKENS,
    }
)
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

# ----------------------------------------------------------------------------
# Initialise conversation on first load
# ----------------------------------------------------------------------------
if not st.session_state.messages:
    # ... existing init logic unchanged ...
    if student_number:
        context_transcript = get_context_transcript(student_number, config_name)
    else:
        context_transcript = None
    if provider == "deepinfra":
        if context_transcript:
            system_prompt = (
                "Context Transcript Summary (provided as context for the Interview):\n\n"
                + f"{context_transcript}\n\n"
                + f"{config.INTERVIEW_OUTLINE}"
            )
        else:
            system_prompt = config.INTERVIEW_OUTLINE
        st.session_state.messages.append({"role": "system", "content": system_prompt})
        st.session_state.messages.append({"role": "user", "content": "Hi"})
    else:
        if context_transcript:
            system_prompt = (
                "Context Transcript Summary (provided as context for the Interview):\n\n"
                + f"{context_transcript}\n\n"
                + f"{config.INTERVIEW_OUTLINE}"
            )
        else:
            system_prompt = config.INTERVIEW_OUTLINE
        st.session_state.messages.append({"role": "system", "content": system_prompt})
        if api == "anthropic":
            st.session_state.messages.append({"role": "user", "content": "Hi"})
    if api == "openai":
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            stream = client.chat.completions.create(**api_kwargs)
            first_reply = st.write_stream(stream)
    else:
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            placeholder = st.empty()
            first_reply = ""
            with client.messages.stream(**api_kwargs) as stream:
                for delta in stream.text_stream:
                    if delta:
                        first_reply += delta
                    placeholder.markdown(first_reply + "▌")
            placeholder.markdown(first_reply)
    st.session_state.messages.append({"role": "assistant", "content": first_reply})
    save_interview_data(student_number=student_number, company_name=company_name)

# ----------------------------------------------------------------------------
# Main chat loop with voice input
# ----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ----- fixed bottom bar ----- */
    .fixed-input-wrapper {
        position: fixed;
        bottom:   0;            /* stick to bottom */
        left:     0;            /* full‑width */
        right:    0;
        padding:  0.75rem 1rem; /* air around components */
        background: var(--background-color, #fff);
        border-top: 1px solid #eee;
        z-index: 9999;          /* on top of other elements */
    }
    /* Prevent Streamlit from adding its own vertical spacing below the bar */
    .fixed-input-wrapper .block-container { padding: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Build the input bar inside a markdown "wrapper" so the CSS above applies.
# The HTML tags are closed immediately after the Streamlit components.
with st.container():
    st.markdown('<div class="fixed-input-wrapper">', unsafe_allow_html=True)
    col_text, col_mic = st.columns([0.8, 0.2])  # 80 / 20

    # Text field (acts like st.chat_input but inside the fixed bar)
    user_typed = col_text.text_input(
        label="Your message here",
        key="typed_msg",
        label_visibility="collapsed",
    )

    # Mic button (records once, returns bytes)
    audio_dict = col_mic.empty().mic_recorder(
        start_prompt="🎙️ Hold to talk",
        stop_prompt="🛑 Release",
        just_once=True,
        use_container_width=True,
        key="voice_msg",
    )

    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Handle input coming from either the text box or the microphone
# ---------------------------------------------------------------------------
message_respondent = None

# 1️⃣  If the user hit the mic button ---------------------------------------
if audio_dict:
    raw_audio = audio_dict.get("bytes", audio_dict)
    with st.spinner("Transcribing …"):
        try:
            transcript = transcribe(raw_audio)
            message_respondent = transcript
            st.markdown(f"**You said:** {transcript}")
        except Exception as e:
            st.error(f"Transcription error: {e}")

# 2️⃣  If the user typed a message ------------------------------------------
if user_typed:
    message_respondent = user_typed
    # Clear the text box so it feels like a chat input
    st.session_state.typed_msg = ""


    # Handle the submitted or transcribed message
    if message_respondent:
        st.session_state.messages.append({"role": "user", "content": message_respondent})
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(message_respondent)

        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            message_interviewer = ""

            # (existing LLM streaming logic unchanged)
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
                st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
                try:
                    save_interview_data(
                        student_number=student_number,
                        company_name=company_name,
                    )
                except Exception:
                    pass

            for code in config.CLOSING_MESSAGES.keys():
                if code in message_interviewer:
                    st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
                    st.session_state.awaiting_email_confirmation = True
                    st.session_state.interview_active = False
                    closing_message = config.CLOSING_MESSAGES[code]
                    st.markdown(closing_message)
                    st.session_state.messages.append({"role": "assistant", "content": closing_message})
                    time.sleep(1)
                    st.rerun()
