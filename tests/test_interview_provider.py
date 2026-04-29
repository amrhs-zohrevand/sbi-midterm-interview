from types import SimpleNamespace

import interview_provider
from interview_provider import (
    OPENROUTER_DEFAULT_MODEL,
    OPENROUTER_INDUSTRY_MODEL,
    OPENROUTER_MIN_REASONING_MAX_TOKENS,
    ModelSelection,
    apply_reasoning_level,
    apply_model_selection_to_openai_kwargs,
    build_openrouter_headers,
    create_provider_runtime,
    normalize_provider,
    resolve_reasoning_experiment_level,
    resolve_model_selection,
)


def test_normalize_provider_handles_claude_models():
    assert normalize_provider("anthropic", "claude-3-5-sonnet") == "anthropic"
    assert normalize_provider("", "claude-3-5-sonnet") == "anthropic"
    assert normalize_provider("openrouter", "openai/gpt-5.4") == "openrouter"
    assert normalize_provider("openrouter", "claude-3-5-sonnet") == "openrouter"


def test_resolve_model_selection_defaults_to_deepseek_for_openrouter():
    selection = resolve_model_selection("openrouter", "midterm_interview", {}, 1024)

    assert selection.model == OPENROUTER_DEFAULT_MODEL
    assert selection.max_tokens == 1024
    assert selection.reasoning == {"enabled": False}
    assert selection.reasoning_level == "none"


def test_resolve_model_selection_uses_deepseek_for_end_reflection():
    selection = resolve_model_selection("openrouter", "end_reflection_interview", {}, 1024)

    assert selection.model == OPENROUTER_DEFAULT_MODEL
    assert selection.max_tokens == 1024
    assert selection.reasoning == {"enabled": False}
    assert selection.reasoning_level == "none"


def test_resolve_model_selection_uses_mimo_without_reasoning_for_industry():
    selection = resolve_model_selection(
        "openrouter",
        "industry_org_survey",
        {},
        1024,
    )

    assert selection.model == OPENROUTER_INDUSTRY_MODEL
    assert selection.max_tokens == OPENROUTER_MIN_REASONING_MAX_TOKENS
    assert selection.reasoning == {"enabled": False}
    assert selection.reasoning_level == "none"


def test_resolve_model_selection_allows_no_reasoning_for_industry():
    selection = resolve_model_selection(
        "openrouter",
        "industry_org_survey",
        {"OPENROUTER_INDUSTRY_REASONING_EFFORT": "none"},
        1024,
    )

    assert selection.model == OPENROUTER_INDUSTRY_MODEL
    assert selection.reasoning == {"enabled": False}
    assert selection.reasoning_level == "none"


def test_apply_reasoning_level_can_force_medium_or_none():
    selection = ModelSelection(model=OPENROUTER_INDUSTRY_MODEL, max_tokens=1536)

    medium_selection = apply_reasoning_level(selection, "medium")
    none_selection = apply_reasoning_level(selection, "none")

    assert medium_selection.reasoning == {"effort": "medium", "exclude": True}
    assert medium_selection.reasoning_level == "medium"
    assert none_selection.reasoning == {"enabled": False}
    assert none_selection.reasoning_level == "none"


def test_resolve_reasoning_experiment_level_honors_boolean_switch():
    disabled = resolve_reasoning_experiment_level(
        False,
        "openrouter",
        "industry_org_survey",
        choice_fn=lambda levels: levels[0],
    )
    enabled = resolve_reasoning_experiment_level(
        True,
        "openrouter",
        "industry_org_survey",
        choice_fn=lambda levels: levels[0],
    )

    assert disabled is None
    assert enabled == "medium"


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


def test_apply_model_selection_to_openai_kwargs_adds_reasoning_fields():
    selection = ModelSelection(
        model=OPENROUTER_INDUSTRY_MODEL,
        max_tokens=OPENROUTER_MIN_REASONING_MAX_TOKENS,
        reasoning={"enabled": False},
    )

    kwargs = apply_model_selection_to_openai_kwargs(
        {"model": "placeholder", "max_tokens": 1024, "messages": [], "stream": True},
        selection,
    )

    assert kwargs["model"] == OPENROUTER_INDUSTRY_MODEL
    assert kwargs["max_tokens"] == OPENROUTER_MIN_REASONING_MAX_TOKENS
    assert kwargs["extra_body"] == {
        "reasoning": {"enabled": False}
    }


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


def test_create_provider_runtime_ignores_model_setting_for_openrouter(monkeypatch):
    calls = []

    def fake_openai(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(kind="openai", kwargs=kwargs)

    monkeypatch.setattr(interview_provider, "OpenAI", fake_openai)

    runtime = create_provider_runtime(
        {
            "API_PROVIDER": "openrouter",
            "MODEL": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
            "OPENROUTER_API_KEY": "test-key",
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
            "default_headers": None,
        }
    ]
