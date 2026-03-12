import base64
import html
import importlib.util
import os
import tempfile
import time
import uuid

import streamlit as st
from openai import OpenAI
from streamlit_mic_recorder import mic_recorder

from database import (
    save_interview_to_sheet,
    update_interview_survey,
    update_interview_summary,
    update_progress_sheet,
)
from interview_completion import (
    INLINE_SURVEY_OPTIONS,
    build_completion_responses,
    completion_panel_copy,
    has_inline_feedback,
    initialize_completion_state,
    survey_option_index,
)
from interview_logic import (
    compose_system_prompt,
    extract_anthropic_text,
    filter_display_messages,
    find_closing_code,
    normalize_query_value,
    should_accept_user_input,
    should_finalize_interview,
)
from interview_persistence import CompletionContext, persist_completion
from interview_selection import get_context_transcript, load_interview_context_map
from interview_smoke import (
    SMOKE_TEST_MODEL,
    next_smoke_reply,
    smoke_generate_summary,
    smoke_noop,
    smoke_test_mode_enabled,
)
from utils import (
    save_interview_data,
    send_transcript_email,
    send_verification_code,
    synthesize_speech_deepinfra,
)

INITIAL_USER_PROMPT = "Please begin the interview following the provided instructions."

SMOKE_TEST_MODE = smoke_test_mode_enabled()

if SMOKE_TEST_MODE:
    provider = "smoke"
    model = SMOKE_TEST_MODEL
    api = "smoke"
    client = None
else:
    provider = st.secrets.get("API_PROVIDER", "openai").lower()
    model = st.secrets.get("MODEL", "gpt-3.5-turbo")

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
            "Unrecognized API provider; supported values are openai, deepinfra, and anthropic."
        )


def get_audio_client():
    """Create an OpenAI client only when voice transcription is requested."""
    api_key = st.secrets.get("API_KEY")
    if not api_key:
        raise RuntimeError("Voice transcription requires API_KEY in Streamlit secrets.")
    return OpenAI(api_key=api_key)


def transcribe(audio_bytes: bytes) -> str:
    """Transcribe recorded audio to text."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name

        with open(tmp_path, "rb") as audio_file:
            response = get_audio_client().audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )

        if hasattr(response, "text"):
            text = response.text
        elif isinstance(response, dict) and "text" in response:
            text = response["text"]
        else:
            text = response

        return text.strip()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def toggle_voice_mode() -> None:
    """Toggle between text and voice input modes."""
    st.session_state.use_voice = not st.session_state.use_voice


def toggle_speech_output() -> None:
    """Toggle speech output for the latest assistant reply."""
    st.session_state.speech_output_enabled = not st.session_state.speech_output_enabled
    if st.session_state.speech_output_enabled:
        _update_tts_audio()


def _get_latest_assistant_message():
    """Return the latest assistant message that is safe to read aloud."""
    for idx in range(len(st.session_state.messages) - 1, -1, -1):
        message = st.session_state.messages[idx]
        if message.get("role") != "assistant":
            continue
        content = message.get("content", "").strip()
        if not content or find_closing_code(content, config.CLOSING_MESSAGES):
            continue
        return idx, content
    return None, ""


def _update_tts_audio():
    """
    Generate TTS audio for the latest assistant response if needed.

    Returns True if new audio was generated, False otherwise.
    """
    if not st.session_state.speech_output_enabled:
        return False

    idx, content = _get_latest_assistant_message()
    if idx is None or not content:
        return False

    tts_model = st.secrets.get("TTS_MODEL", "hexgrad/Kokoro-82M")
    tts_voice = st.secrets.get("TTS_VOICE", "af_heart")
    tts_key = st.secrets.get("DEEPINFRA_API_KEY")
    cache_key = f"{idx}:{tts_voice}"
    if (
        st.session_state.tts_cache_key == cache_key
        and st.session_state.tts_audio_bytes
    ):
        return False

    try:
        with st.spinner("Generating speech output..."):
            audio_bytes, mime_type = synthesize_speech_deepinfra(
                content,
                model=tts_model,
                api_key=tts_key,
                voice=tts_voice,
            )
        st.session_state.tts_audio_bytes = audio_bytes
        st.session_state.tts_audio_mime = mime_type
        st.session_state.tts_cache_key = cache_key
        st.session_state.tts_last_message_idx = idx
        st.session_state.tts_autoplay_nonce += 1
        return True
    except Exception as exc:
        st.error(f"Speech output failed: {exc}")
        return False


query_params = st.query_params
raw_config_name = normalize_query_value(query_params.get("interview_config"), "Default")
if raw_config_name == "Default":
    import config

    config_name = "Default"
else:
    config_name = raw_config_name
    config_path = os.path.join(
        os.path.dirname(__file__), "interview_configs", f"{config_name}.py"
    )
    if not os.path.exists(config_path):
        st.error(f"Configuration file {config_name}.py not found.")
        st.stop()
    spec = importlib.util.spec_from_file_location("config", config_path)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)


def _get_param(name: str, default: str = "") -> str:
    """Return a query parameter as a decoded string."""
    return html.unescape(normalize_query_value(query_params.get(name), default))


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
if "use_voice" not in st.session_state:
    st.session_state.use_voice = False
if "student_verified" not in st.session_state:
    st.session_state.student_verified = False
if "verification_code" not in st.session_state:
    st.session_state.verification_code = ""
if "verification_code_sent" not in st.session_state:
    st.session_state.verification_code_sent = False
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = ""
if "completion_saved" not in st.session_state:
    st.session_state.completion_saved = False
if "speech_output_enabled" not in st.session_state:
    st.session_state.speech_output_enabled = False
if "tts_audio_bytes" not in st.session_state:
    st.session_state.tts_audio_bytes = None
if "tts_audio_mime" not in st.session_state:
    st.session_state.tts_audio_mime = ""
if "tts_last_message_idx" not in st.session_state:
    st.session_state.tts_last_message_idx = None
if "tts_cache_key" not in st.session_state:
    st.session_state.tts_cache_key = ""
if "tts_autoplay_nonce" not in st.session_state:
    st.session_state.tts_autoplay_nonce = 0
if "tts_played_nonce" not in st.session_state:
    st.session_state.tts_played_nonce = 0


required_params = ["name", "recipient_email"]


def validate_query_params(params):
    missing = [
        key for key in required_params if not normalize_query_value(params.get(key))
    ]
    return len(missing) == 0, missing


def get_chat_messages():
    """Return the current conversation in provider-compatible format."""
    if api == "anthropic":
        return [
            message
            for message in st.session_state.messages
            if message["role"] != "system"
        ]
    return list(st.session_state.messages)


def build_chat_kwargs(messages=None, stream=True):
    """Build provider-specific chat kwargs for the current conversation state."""
    conversation = list(messages if messages is not None else get_chat_messages())
    kwargs = {
        "model": model,
        "max_tokens": config.MAX_OUTPUT_TOKENS,
        "messages": conversation,
        "stream": stream,
    }
    if config.TEMPERATURE is not None:
        kwargs["temperature"] = config.TEMPERATURE
    if api == "anthropic":
        kwargs["system"] = st.session_state.system_prompt
        kwargs["messages"] = [
            message for message in conversation if message["role"] != "system"
        ]
    return kwargs


def stream_assistant_reply(message_placeholder, messages=None) -> str:
    """Stream the assistant response for the current provider."""
    if SMOKE_TEST_MODE:
        reply = next_smoke_reply(messages if messages is not None else get_chat_messages())
        if len(reply) > 5:
            message_placeholder.markdown(reply + "▌")
        return reply

    reply = ""
    if api == "openai":
        stream = client.chat.completions.create(**build_chat_kwargs(messages=messages))
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                reply += delta
            if len(reply) > 5:
                message_placeholder.markdown(reply + "▌")
            if find_closing_code(reply, config.CLOSING_MESSAGES):
                message_placeholder.empty()
                break
        return reply

    with client.messages.stream(**build_chat_kwargs(messages=messages)) as stream:
        for delta in stream.text_stream:
            if delta:
                reply += delta
            if len(reply) > 5:
                message_placeholder.markdown(reply + "▌")
            if find_closing_code(reply, config.CLOSING_MESSAGES):
                message_placeholder.empty()
                break
    return reply


def persist_local_transcript():
    """Persist the local transcript and time files for the current interview."""
    return save_interview_data(
        student_number=student_number,
        company_name=company_name,
        transcripts_directory=config.TRANSCRIPTS_DIRECTORY,
        times_directory=config.TIMES_DIRECTORY,
    )


def generate_summary(transcript_text: str) -> str:
    """Generate a concise summary of the completed interview."""
    if not transcript_text.strip():
        return "No transcript available."
    if SMOKE_TEST_MODE:
        return smoke_generate_summary(transcript_text)

    summary_prompt = (
        "Please provide a concise but detailed summary for the following interview transcript:\n\n"
        + transcript_text
    )

    if api == "openai":
        if provider == "deepinfra":
            summary_messages = [{"role": "user", "content": summary_prompt}]
        else:
            summary_messages = [
                {
                    "role": "system",
                    "content": "You create concise but detailed summaries of interview transcripts.",
                },
                {"role": "user", "content": summary_prompt},
            ]
        response = client.chat.completions.create(
            model=model,
            messages=summary_messages,
            max_tokens=200,
            temperature=0.7,
            stream=False,
        )
        return response.choices[0].message.content.strip()

    response = client.messages.create(
        model=model,
        system="You create concise but detailed summaries of interview transcripts.",
        messages=[{"role": "user", "content": summary_prompt}],
        max_tokens=200,
        temperature=0.7,
    )
    summary_text = extract_anthropic_text(response)
    return summary_text or "Summary generation returned no text."


def finalize_interview(send_email=False, email_input=None):
    """Persist the finished interview and move the UI to the evaluation state."""
    if st.session_state.completion_saved:
        return

    completion_responses = build_completion_responses(st.session_state)
    completion_context = CompletionContext(
        interview_id=st.session_state.session_id,
        student_number=student_number,
        respondent_name=respondent_name,
        company_name=company_name,
        config_name=config_name,
        recipient_email=recipient_email,
        start_time=st.session_state.start_time,
        messages=list(st.session_state.messages),
        completion_responses=completion_responses,
    )
    completion_result = persist_completion(
        completion_context,
        persist_local_transcript=persist_local_transcript,
        send_transcript_email=smoke_noop if SMOKE_TEST_MODE else send_transcript_email,
        save_interview_to_sheet=smoke_noop if SMOKE_TEST_MODE else save_interview_to_sheet,
        update_progress_sheet=smoke_noop if SMOKE_TEST_MODE else update_progress_sheet,
        generate_summary=generate_summary,
        update_interview_summary=smoke_noop
        if SMOKE_TEST_MODE
        else update_interview_summary,
        update_interview_survey=smoke_noop if SMOKE_TEST_MODE else update_interview_survey,
    )
    st.session_state.transcript_link = completion_result.transcript_link
    st.session_state.transcript_file = completion_result.transcript_file
    st.session_state.email_sent = completion_result.email_sent

    st.session_state.completion_saved = True
    st.session_state.show_evaluation_only = True


is_valid, missing = validate_query_params(query_params)
if not is_valid:
    st.error(f"Missing parameters: {', '.join(missing)}")
    st.stop()

student_number = _get_param("student_number", "")
respondent_name = _get_param("name")
recipient_email = _get_param("recipient_email")
company_name = _get_param("company")

initialize_completion_state(st.session_state, recipient_email)

if not st.session_state.system_prompt:
    stored_system_prompt = next(
        (
            message["content"]
            for message in st.session_state.messages
            if message["role"] == "system"
        ),
        "",
    )
    st.session_state.system_prompt = stored_system_prompt

DEFAULT_QUALTRICS_URL = "https://leidenuniv.eu.qualtrics.com/jfe/form/SV_agZpa5UeS9sUwLQ"
evaluation_url = getattr(config, "POST_INTERVIEW_SURVEY_URL", DEFAULT_QUALTRICS_URL)
evaluation_url_with_session = (
    f"{evaluation_url}?session_id={st.session_state.session_id}"
)

context_map = load_interview_context_map()
needs_context = bool(student_number) and config_name.lower() in context_map
if needs_context and not st.session_state.student_verified:
    if not st.session_state.verification_code_sent:
        code = f"{uuid.uuid4().int % 1000000:06d}"
        st.session_state.verification_code = code
        send_verification_code(student_number, code)
        st.session_state.verification_code_sent = True
        st.info(
            f"A verification code has been sent to {student_number}@vuw.leidenuniv.nl"
        )

    user_code = st.text_input(
        "Enter the verification code sent to your university email:", ""
    )
    if st.button("Verify Code"):
        if user_code.strip() == st.session_state.verification_code:
            st.session_state.student_verified = True
            st.success("Verification successful. Loading interview...")
            st.rerun()
        else:
            st.error("Incorrect code. Please try again.")
    st.stop()

if st.session_state.show_evaluation_only:
    survey_saved = has_inline_feedback(build_completion_responses(st.session_state))
    st.success("Your interview has been saved.")
    if SMOKE_TEST_MODE:
        st.caption("Smoke test mode is enabled: no external model, email, or remote database calls were made.")
    if survey_saved:
        st.caption("Your quick in-app feedback was saved too. Thank you.")
    st.markdown(
        f"""
        <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; margin-top: 2em; gap: 1rem;">
            <div style="max-width: 640px; text-align: center; color: #444;">
                If you would like to complete the longer follow-up survey as well, you can continue below.
            </div>
            <a href="{evaluation_url_with_session}" target="_blank"
               style="text-decoration: none; background-color: #4CAF50; color: white;
                      padding: 15px 32px; text-align: center; font-size: 16px;
                      border-radius: 8px;">
               Open the full follow-up survey
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


st.sidebar.title("Interview Details")
for param in required_params:
    label = param.replace("_", " ").capitalize()
    value = html.unescape(normalize_query_value(query_params.get(param)))
    st.sidebar.write(f"{label}: {value}")
if company_name:
    st.sidebar.write(f"Company: {company_name}")
if student_number:
    st.sidebar.write(f"Student number: {student_number}")
st.sidebar.write(f"Session ID: {st.session_state.session_id}")


if should_finalize_interview(
    st.session_state.interview_active,
    st.session_state.awaiting_email_confirmation,
    st.session_state.completion_saved,
):
    finalize_interview()
    st.rerun()


if len(st.session_state.messages) > 5:
    st.markdown(
        """
        <div style="text-align: center; color: #666; font-size: 0.9em; margin: 0.5rem 0 1rem 0;
                    padding: 0.5rem; background-color: rgba(128,128,128,0.05); border-radius: 4px;">
            👇 Scroll down to reply 👇
        </div>
        """,
        unsafe_allow_html=True,
    )

conversation_container = st.container()
with conversation_container:
    for message in filter_display_messages(
        st.session_state.messages, config.CLOSING_MESSAGES
    ):
        avatar = (
            config.AVATAR_INTERVIEWER
            if message["role"] == "assistant"
            else config.AVATAR_RESPONDENT
        )
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])


if st.session_state.awaiting_email_confirmation:
    st.markdown("---")
    panel_title, panel_body, can_continue = completion_panel_copy(
        st.session_state.interview_active
    )
    st.subheader(panel_title)
    st.write(panel_body)
    if can_continue and st.button("Continue Interview", key="continue_interview"):
        st.session_state.awaiting_email_confirmation = False
        st.rerun()

    with st.form("completion_form"):
        completion_email_input = st.text_input(
            "Confirm or update your email address:",
            value=st.session_state.completion_email or recipient_email,
        )
        completion_send_email = st.checkbox(
            "Email me a transcript of this interview",
            value=bool(st.session_state.completion_send_email),
        )
        st.caption("Optional quick feedback")
        survey_col1, survey_col2 = st.columns(2)
        with survey_col1:
            completion_survey_usefulness = st.selectbox(
                "How useful was this interview?",
                INLINE_SURVEY_OPTIONS,
                index=survey_option_index(
                    st.session_state.completion_survey_usefulness
                ),
            )
        with survey_col2:
            completion_survey_naturalness = st.selectbox(
                "How natural did the conversation feel?",
                INLINE_SURVEY_OPTIONS,
                index=survey_option_index(
                    st.session_state.completion_survey_naturalness
                ),
            )
        completion_survey_feedback = st.text_area(
            "Anything we should improve?",
            value=st.session_state.completion_survey_feedback,
            height=120,
        )
        finish_submitted = st.form_submit_button(
            "Save and Finish",
            use_container_width=True,
        )

    if finish_submitted:
        st.session_state.completion_email = (
            completion_email_input.strip() or recipient_email
        )
        st.session_state.completion_send_email = bool(completion_send_email)
        st.session_state.completion_survey_usefulness = (
            completion_survey_usefulness
        )
        st.session_state.completion_survey_naturalness = (
            completion_survey_naturalness
        )
        st.session_state.completion_survey_feedback = completion_survey_feedback
        if st.session_state.interview_active:
            st.session_state.interview_active = False
            quit_msg = "You have cancelled the interview."
            st.session_state.messages.append({"role": "assistant", "content": quit_msg})
        st.session_state.awaiting_email_confirmation = False
        with st.spinner("Saving your interview..."):
            completion_responses = build_completion_responses(st.session_state)
            finalize_interview(
                send_email=completion_responses.send_email,
                email_input=completion_responses.email,
            )
        st.rerun()


if not st.session_state.messages:
    if student_number and st.session_state.student_verified:
        context_transcript = get_context_transcript(student_number, config_name)
    else:
        context_transcript = None

    base_prompt = getattr(config, "SYSTEM_PROMPT", config.INTERVIEW_OUTLINE)
    system_prompt = compose_system_prompt(base_prompt, context_transcript)
    st.session_state.system_prompt = system_prompt

    initial_messages = [{"role": "user", "content": INITIAL_USER_PROMPT}]
    if api == "openai":
        st.session_state.messages.append({"role": "system", "content": system_prompt})
        initial_messages = list(st.session_state.messages) + initial_messages

    with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
        placeholder = st.empty()
        first_reply = stream_assistant_reply(placeholder, messages=initial_messages)

    closing_code = find_closing_code(first_reply, config.CLOSING_MESSAGES)
    if closing_code:
        first_reply = config.CLOSING_MESSAGES[closing_code]
        placeholder.markdown(first_reply)
        st.session_state.awaiting_email_confirmation = True
        st.session_state.interview_active = False
    else:
        placeholder.markdown(first_reply)

    st.session_state.messages.append({"role": "assistant", "content": first_reply})
    persist_local_transcript()
    if st.session_state.speech_output_enabled and _update_tts_audio():
        st.rerun()


if should_accept_user_input(
    st.session_state.interview_active,
    st.session_state.awaiting_email_confirmation,
):
    message_respondent = None

    st.markdown(
        """
        <style>
        .stChatMessage {
            margin-bottom: 1rem;
        }

        .stChatMessage:last-child {
            margin-bottom: 1.5rem;
        }

        .main .block-container {
            padding-bottom: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")
    input_container = st.container()

    if st.session_state.use_voice:
        voice_col, text_col, speech_col = input_container.columns([0.08, 0.84, 0.08])
        with text_col:
            audio_dict = mic_recorder(
                start_prompt="🎙️ Hold to talk",
                stop_prompt="🛑 Release",
                just_once=True,
                use_container_width=True,
                key="mic_recorder",
            )
        with voice_col:
            st.button(
                "⌨️",
                on_click=toggle_voice_mode,
                use_container_width=True,
                disabled=SMOKE_TEST_MODE,
            )
        with speech_col:
            speech_icon = "🔇" if st.session_state.speech_output_enabled else "🔊"
            st.button(
                speech_icon,
                on_click=toggle_speech_output,
                use_container_width=True,
                help="Toggle speech output for the latest assistant reply",
                disabled=SMOKE_TEST_MODE,
            )
        if audio_dict:
            raw_audio = (
                audio_dict["bytes"]
                if isinstance(audio_dict, dict) and "bytes" in audio_dict
                else audio_dict
            )
            with st.spinner("Transcribing..."):
                try:
                    transcript = transcribe(raw_audio)
                except Exception as exc:
                    st.error(f"Transcription error: {exc}")
                    transcript = ""
                if transcript:
                    message_respondent = transcript
                    st.markdown(f"**You said:** {transcript}")
    else:
        text_col, voice_col, speech_col = input_container.columns([0.84, 0.08, 0.08])
        with text_col:
            message_respondent = st.chat_input("Your message here")
        with voice_col:
            st.button(
                "🎤",
                on_click=toggle_voice_mode,
                use_container_width=True,
                disabled=SMOKE_TEST_MODE,
            )
        with speech_col:
            speech_icon = "🔇" if st.session_state.speech_output_enabled else "🔊"
            st.button(
                speech_icon,
                on_click=toggle_speech_output,
                use_container_width=True,
                help="Toggle speech output for the latest assistant reply",
                disabled=SMOKE_TEST_MODE,
            )

    if st.session_state.speech_output_enabled and st.session_state.tts_audio_bytes:
        audio_b64 = base64.b64encode(st.session_state.tts_audio_bytes).decode("ascii")
        mime_type = st.session_state.tts_audio_mime or "audio/wav"
        should_autoplay = (
            st.session_state.tts_autoplay_nonce > st.session_state.tts_played_nonce
        )
        autoplay_attr = "autoplay" if should_autoplay else ""
        if should_autoplay:
            st.session_state.tts_played_nonce = st.session_state.tts_autoplay_nonce
        current_voice = st.secrets.get("TTS_VOICE", "af_heart")
        st.markdown(
            f"""
            <style>
            audio {{
                width: 100%;
            }}
            </style>
            <audio controls {autoplay_attr}>
                <source src="data:{mime_type};base64,{audio_b64}">
            </audio>
            """,
            unsafe_allow_html=True,
        )
        st.caption(f"Voice: {current_voice}")

    if message_respondent:
        st.session_state.messages.append({"role": "user", "content": message_respondent})

        with conversation_container:
            with st.chat_message("user", avatar=config.AVATAR_RESPONDENT):
                st.markdown(message_respondent)

        with conversation_container:
            with st.chat_message("assistant", avatar=config.AVATAR_INTERVIEWER):
                placeholder = st.empty()
                assistant_reply = stream_assistant_reply(placeholder)

                closing_code = find_closing_code(
                    assistant_reply, config.CLOSING_MESSAGES
                )
                if not closing_code:
                    placeholder.markdown(assistant_reply)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": assistant_reply}
                    )
                    persist_local_transcript()
                    if (
                        st.session_state.speech_output_enabled
                        and _update_tts_audio()
                    ):
                        st.rerun()
                else:
                    st.session_state.awaiting_email_confirmation = True
                    st.session_state.interview_active = False
                    closing_message = config.CLOSING_MESSAGES[closing_code]
                    placeholder.markdown(closing_message)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": closing_message}
                    )
                    persist_local_transcript()
                    if st.session_state.speech_output_enabled and _update_tts_audio():
                        st.rerun()
                    time.sleep(1)
                    st.rerun()

    if st.button("Finish interview", key="finish_interview_bottom", use_container_width=True):
        st.session_state.awaiting_email_confirmation = True
        st.rerun()
