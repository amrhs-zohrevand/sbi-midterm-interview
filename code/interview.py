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
from st_mic_recorder import mic_recorder
import tempfile

# ----------------------------------------------------------------------------
# API client setup
# ----------------------------------------------------------------------------
provider = st.secrets.get("API_PROVIDER", "openai").lower()
model = st.secrets.get("MODEL", "gpt-3.5-turbo")

from openai import OpenAI

# Primary LLM client
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

# Whisper (OpenAI) transcription client (used for voice input regardless of provider)
_openai_whisper_key = st.secrets.get("OPENAI_API_KEY", None)
whisper_client = OpenAI(api_key=_openai_whisper_key) if _openai_whisper_key else None

def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe audio bytes using OpenAI Whisper.
    """
    if not whisper_client:
        st.error("OpenAI API key for Whisper not configured.")
        return ""
    # Write to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    # Send to Whisper
    with open(tmp_path, "rb") as f:
        resp = whisper_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text"
        )
    return resp.text.strip()

# ----------------------------------------------------------------------------
# Configuration loading
# ----------------------------------------------------------------------------
ENV = st.secrets.get("ENV", "production")
query_params = st.query_params
if "interview_config" not in query_params:
    import config  # local default
    config_name = "Default"
else:
    config_name = st.query_params.get("interview_config", ["Default"])[0]
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
# Validate required params
# ----------------------------------------------------------------------------
required_params = ["name", "recipient_email"]
def validate_query_params(params):
    missing = [k for k in required_params if k not in params or not params[k]]
    return len(missing) == 0, missing

is_valid, missing = validate_query_params(query_params)
if not is_valid:
    st.error(f"Missing parameters: {', '.join(missing)}")
    st.stop()

student_number = _get_param("student_number", "")
respondent_name = _get_param("name")
recipient_email = _get_param("recipient_email")
company_name = _get_param("company")

# Qualtrics survey link
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
# Early exit: evaluation-only view
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
# Sidebar details
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
# Top banner Quit button
# ----------------------------------------------------------------------------
col1, col2 = st.columns([0.85, 0.15])
with col2:
    if st.session_state.interview_active and not st.session_state.awaiting_email_confirmation:
        if st.button("Quit"):
            st.session_state.awaiting_email_confirmation = True

# ... (quit & post-interview flows unchanged) ...

# ----------------------------------------------------------------------------
# Render prior conversation
# ----------------------------------------------------------------------------
for message in st.session_state.messages[1:]:
    avatar = (
        config.AVATAR_INTERVIEWER if message["role"] == "assistant"
        else config.AVATAR_RESPONDENT
    )
    if not any(
        code in message["content"] for code in config.CLOSING_MESSAGES.keys()
    ):
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

# ----------------------------------------------------------------------------
# Prepare LLM call kwargs
# ----------------------------------------------------------------------------
api_kwargs = {"stream": True}
if api == "anthropic":
    api_kwargs["system"] = st.secrets.get(
        "SYSTEM_PROMPT", "Your default system prompt"
    )
api_kwargs.update({
    "messages": st.session_state.messages,
    "model": model,
    "max_tokens": config.MAX_OUTPUT_TOKENS,
})
if config.TEMPERATURE is not None:
    api_kwargs["temperature"] = config.TEMPERATURE

# ----------------------------------------------------------------------------
# Initialise conversation on first load (unchanged)
# ----------------------------------------------------------------------------
# ... existing first-load logic ...

# ----------------------------------------------------------------------------
# Main chat loop with voice input support
# ----------------------------------------------------------------------------
if st.session_state.interview_active:
    # Toggle between text and voice input
    use_voice = st.checkbox("🎤 Voice input")
    message_respondent = None

    if use_voice:
        audio_bytes = mic_recorder(
            start_prompt="🎙️ Hold to talk",
            stop_prompt="🛑 Release",
            just_once=True,
            use_container_width=True,
        )
        if audio_bytes:
            text = transcribe_audio(audio_bytes)
            if text:
                message_respondent = text
                st.markdown(f"**You said:** {text}")
    else:
        message_respondent = st.chat_input("Your message here")

    if message_respondent:
        # Append user message
        st.session_state.messages.append({"role": "user", "content": message_respondent})
        with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
            st.markdown(message_respondent)

        # Assistant response (unchanged streaming logic)
        with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
            message_placeholder = st.empty()
            message_interviewer = ""

            if api == "openai":
                stream = client.chat.completions.create(**api_kwargs)
                for message in stream:
                    delta = message.choices[0].delta.content
                    if delta:
                        message_interviewer += delta
                        message_placeholder.markdown(message_interviewer + "▌")
                    if any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                        message_placeholder.empty()
                        break

            elif api == "anthropic":
                with client.messages.stream(**api_kwargs) as stream:
                    for delta in stream.text_stream:
                        if delta:
                            message_interviewer += delta
                            message_placeholder.markdown(message_interviewer + "▌")
                        if any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                            message_placeholder.empty()
                            break

            # Finalize response
            if not any(code in message_interviewer for code in config.CLOSING_MESSAGES.keys()):
                message_placeholder.markdown(message_interviewer)
                st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
                try:
                    save_interview_data(student_number=student_number, company_name=company_name)
                except Exception:
                    pass

            # Check for closing codes
            for code, closing_message in config.CLOSING_MESSAGES.items():
                if code in message_interviewer:
                    st.session_state.messages.append({"role": "assistant", "content": message_interviewer})
                    st.session_state.awaiting_email_confirmation = True
                    st.session_state.interview_active = False
                    st.markdown(closing_message)
                    st.session_state.messages.append({"role": "assistant", "content": closing_message})
                    time.sleep(1)
                    st.rerun()
