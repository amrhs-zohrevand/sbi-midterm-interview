from types import SimpleNamespace

import interview_provider
from interview_provider import (
    OPENAI_DEFAULT_MODEL,
    OPENAI_DEFAULT_REASONING_EFFORT,
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_INDUSTRY_MODEL,
    OPENROUTER_MIN_REASONING_MAX_TOKENS,
    ModelSelection,
    apply_model_selection_to_openai_kwargs,
    build_summary_request_kwargs,
    build_openrouter_headers,
    create_provider_runtime,
    normalize_provider,
    resolve_model_selection,
)


def test_normalize_provider_handles_claude_models():
    assert normalize_provider("anthropic", "claude-3-5-sonnet") == "anthropic"
    assert normalize_provider("openrouter", "claude-3-5-sonnet") == "anthropic"
    assert normalize_provider("openrouter", "openai/gpt-5.4") == "openrouter"


def test_resolve_model_selection_defaults_to_qwen_for_openrouter():
    selection = resolve_model_selection("openrouter", "midterm_interview", {}, 1024)

    assert selection.model == OPENROUTER_DEFAULT_MODEL
    assert selection.max_tokens == 1024
    assert selection.extra_body_reasoning == {"enabled": False}


def test_resolve_model_selection_defaults_to_openai_gpt54_nano_with_medium_reasoning():
    selection = resolve_model_selection("openai", "midterm_interview", {}, 1024)

    assert selection.model == OPENAI_DEFAULT_MODEL
    assert selection.max_tokens == 1024
    assert selection.reasoning_effort == OPENAI_DEFAULT_REASONING_EFFORT


def test_resolve_model_selection_uses_gpt54_reasoning_for_industry():
    selection = resolve_model_selection(
        "openrouter",
        "industry_org_survey",
        {},
        1024,
    )

    assert selection.model == OPENROUTER_INDUSTRY_MODEL
    assert selection.max_tokens == OPENROUTER_MIN_REASONING_MAX_TOKENS
    assert selection.extra_body_reasoning == {"effort": "minimal", "exclude": True}


def test_build_openrouter_headers_only_includes_present_values():
    headers = build_openrouter_headers(
        {
            "OPENROUTER_SITE_URL": "http://localhost:8501",
            "OPENROUTER_APP_NAME": "Interview App",
        }
    )

    assert headers == {
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "Interview App",
    }
    assert build_openrouter_headers({}) == {}


def test_apply_model_selection_to_openai_kwargs_adds_openai_reasoning_effort():
    selection = ModelSelection(
        model=OPENAI_DEFAULT_MODEL,
        max_tokens=1024,
        reasoning_effort="medium",
    )

    kwargs = apply_model_selection_to_openai_kwargs(
        {"model": "placeholder", "max_tokens": 256, "messages": [], "stream": True},
        "openai",
        selection,
    )

    assert kwargs["model"] == OPENAI_DEFAULT_MODEL
    assert kwargs["max_completion_tokens"] == 1024
    assert kwargs["reasoning_effort"] == "medium"
    assert "max_tokens" not in kwargs
    assert "extra_body" not in kwargs


def test_apply_model_selection_to_openai_kwargs_keeps_openrouter_reasoning_fields():
    selection = ModelSelection(
        model=OPENROUTER_INDUSTRY_MODEL,
        max_tokens=OPENROUTER_MIN_REASONING_MAX_TOKENS,
        extra_body_reasoning={"effort": "minimal", "exclude": True},
    )

    kwargs = apply_model_selection_to_openai_kwargs(
        {"model": "placeholder", "max_tokens": 1024, "messages": [], "stream": True},
        "openrouter",
        selection,
    )

    assert kwargs["model"] == OPENROUTER_INDUSTRY_MODEL
    assert kwargs["max_tokens"] == OPENROUTER_MIN_REASONING_MAX_TOKENS
    assert kwargs["extra_body"] == {
        "reasoning": {"effort": "minimal", "exclude": True}
    }


def test_apply_model_selection_to_openai_kwargs_leaves_deepinfra_plain():
    selection = ModelSelection(
        model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        max_tokens=1024,
    )

    kwargs = apply_model_selection_to_openai_kwargs(
        {"model": "placeholder", "max_tokens": 256, "messages": [], "stream": True},
        "deepinfra",
        selection,
    )

    assert kwargs == {
        "model": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "max_tokens": 1024,
        "messages": [],
        "stream": True,
    }


def test_build_summary_request_kwargs_uses_openai_model_and_omits_temperature_with_reasoning():
    kwargs = build_summary_request_kwargs(
        provider="openai",
        model_selection=ModelSelection(
            model=OPENAI_DEFAULT_MODEL,
            max_tokens=1024,
            reasoning_effort="medium",
        ),
        summary_prompt="Summarize this interview.",
        temperature=0.7,
    )

    assert kwargs["model"] == OPENAI_DEFAULT_MODEL
    assert kwargs["stream"] is False
    assert kwargs["max_completion_tokens"] == 200
    assert kwargs["reasoning_effort"] == "medium"
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1] == {
        "role": "user",
        "content": "Summarize this interview.",
    }


def test_build_summary_request_kwargs_keeps_temperature_for_deepinfra():
    kwargs = build_summary_request_kwargs(
        provider="deepinfra",
        model_selection=ModelSelection(
            model="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            max_tokens=1024,
        ),
        summary_prompt="Summarize this interview.",
        temperature=0.7,
    )

    assert kwargs["model"] == "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
    assert kwargs["stream"] is False
    assert kwargs["temperature"] == 0.7
    assert kwargs["messages"] == [
        {"role": "user", "content": "Summarize this interview."}
    ]


def test_apply_model_selection_to_openai_kwargs_never_sends_max_tokens_for_openai():
    selection = ModelSelection(
        model=OPENAI_DEFAULT_MODEL,
        max_tokens=512,
        reasoning_effort="medium",
    )

    kwargs = apply_model_selection_to_openai_kwargs(
        {"model": "placeholder", "messages": [], "stream": True, "max_tokens": 999},
        "openai",
        selection,
    )

    assert kwargs["max_completion_tokens"] == 512
    assert "max_tokens" not in kwargs


def test_create_provider_runtime_builds_openai_client(monkeypatch):
    calls = []

    def fake_openai(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(kind="openai", kwargs=kwargs)

    monkeypatch.setattr(interview_provider, "OpenAI", fake_openai)

    runtime = create_provider_runtime(
        {
            "API_PROVIDER": "openai",
            "API_KEY": "test-key",
        },
        "midterm_interview",
        1024,
    )

    assert runtime.provider == "openai"
    assert runtime.api == "openai"
    assert runtime.model_selection.model == OPENAI_DEFAULT_MODEL
    assert runtime.model_selection.reasoning_effort == OPENAI_DEFAULT_REASONING_EFFORT
    assert calls == [{"api_key": "test-key"}]


def test_create_provider_runtime_builds_openrouter_client(monkeypatch):
    calls = []

    def fake_openai(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(kind="openai", kwargs=kwargs)

    monkeypatch.setattr(interview_provider, "OpenAI", fake_openai)

    runtime = create_provider_runtime(
        {
            "API_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_SITE_URL": "http://localhost:8501",
            "OPENROUTER_APP_NAME": "Interview App",
        },
        "industry_org_survey",
        1024,
    )

    assert runtime.provider == "openrouter"
    assert runtime.api == "openai"
    assert runtime.model_selection.model == OPENROUTER_INDUSTRY_MODEL
    assert calls == [
        {
            "api_key": "test-key",
            "base_url": interview_provider.OPENROUTER_BASE_URL,
            "default_headers": {
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "Interview App",
            },
        }
    ]
