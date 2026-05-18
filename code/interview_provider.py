from dataclasses import dataclass
from typing import Callable, Sequence

from openai import OpenAI


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "qwen/qwen3.5-35b-a3b"
OPENROUTER_INDUSTRY_MODEL = "openai/gpt-5.4"
OPENROUTER_DEFAULT_REASONING_EFFORT = "minimal"
OPENROUTER_MIN_REASONING_MAX_TOKENS = 1536
OPENROUTER_INDUSTRY_CONFIGS = {"industry_org_survey"}
OPENROUTER_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high"}
REASONING_EXPERIMENT_LEVELS = ("medium", "none")


@dataclass(frozen=True)
class ModelSelection:
    model: str
    max_tokens: int
    reasoning: dict | None = None
    reasoning_level: str = "none"


@dataclass(frozen=True)
class ProviderRuntime:
    provider: str
    api: str
    client: object
    model_selection: ModelSelection


def normalize_provider(provider_name: str, model_name: str = "") -> str:
    """Normalize the configured provider name for downstream branching."""
    provider = (provider_name or "").strip().lower()
    if provider in {"openai", "deepinfra", "openrouter", "anthropic"}:
        return provider
    if "claude" in model_name.lower():
        return "anthropic"
    return "openai"


def _normalize_reasoning_effort(raw_effort: str) -> str:
    effort = (raw_effort or OPENROUTER_DEFAULT_REASONING_EFFORT).strip().lower()
    if effort not in OPENROUTER_REASONING_EFFORTS:
        return OPENROUTER_DEFAULT_REASONING_EFFORT
    return effort


def supports_reasoning_experiment(provider: str, config_name: str) -> bool:
    return provider == "openrouter" and config_name in OPENROUTER_INDUSTRY_CONFIGS


def resolve_reasoning_experiment_level(
    enabled: bool,
    provider: str,
    config_name: str,
    *,
    choice_fn: Callable[[Sequence[str]], str],
) -> str | None:
    if not enabled:
        return None
    if not supports_reasoning_experiment(provider, config_name):
        return None
    return choice_fn(REASONING_EXPERIMENT_LEVELS)


def reasoning_payload_for_level(reasoning_level: str) -> dict:
    normalized_level = _normalize_reasoning_effort(reasoning_level)
    if normalized_level == "none":
        return {"enabled": False}
    return {"effort": normalized_level, "exclude": True}


def apply_reasoning_level(
    model_selection: ModelSelection, reasoning_level: str
) -> ModelSelection:
    normalized_level = _normalize_reasoning_effort(reasoning_level)
    return ModelSelection(
        model=model_selection.model,
        max_tokens=model_selection.max_tokens,
        reasoning=reasoning_payload_for_level(normalized_level),
        reasoning_level=normalized_level,
    )


def build_openrouter_headers(secrets) -> dict[str, str]:
    """Return optional attribution headers for OpenRouter requests."""
    headers = {}
    referer = str(secrets.get("OPENROUTER_SITE_URL", "")).strip()
    title = str(secrets.get("OPENROUTER_APP_NAME", "")).strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def apply_model_selection_to_openai_kwargs(kwargs: dict, model_selection: ModelSelection) -> dict:
    """Apply model-selection overrides to an OpenAI-compatible request payload."""
    updated = dict(kwargs)
    updated["model"] = model_selection.model
    updated["max_tokens"] = model_selection.max_tokens
    if model_selection.reasoning:
        updated["extra_body"] = {"reasoning": dict(model_selection.reasoning)}
    return updated


def resolve_model_selection(provider: str, config_name: str, secrets, default_max_tokens: int) -> ModelSelection:
    """Select the active model and request settings for the given provider/config."""
    if provider != "openrouter":
        return ModelSelection(
            model=str(secrets.get("MODEL", "gpt-3.5-turbo")),
            max_tokens=default_max_tokens,
            reasoning_level="none",
        )

    if config_name in OPENROUTER_INDUSTRY_CONFIGS:
        reasoning_effort = _normalize_reasoning_effort(
            str(
                secrets.get(
                    "OPENROUTER_INDUSTRY_REASONING_EFFORT",
                    OPENROUTER_DEFAULT_REASONING_EFFORT,
                )
            )
        )
        reasoning_max_tokens = int(
            secrets.get(
                "OPENROUTER_REASONING_MAX_TOKENS",
                OPENROUTER_MIN_REASONING_MAX_TOKENS,
            )
        )
        return ModelSelection(
            model=str(
                secrets.get("OPENROUTER_INDUSTRY_MODEL", OPENROUTER_INDUSTRY_MODEL)
            ),
            max_tokens=max(default_max_tokens, reasoning_max_tokens),
            reasoning=reasoning_payload_for_level(reasoning_effort),
            reasoning_level=reasoning_effort,
        )

    return ModelSelection(
        model=str(secrets.get("OPENROUTER_DEFAULT_MODEL", OPENROUTER_DEFAULT_MODEL)),
        max_tokens=default_max_tokens,
        reasoning={"enabled": False},
        reasoning_level="none",
    )


def create_provider_runtime(secrets, config_name: str, default_max_tokens: int) -> ProviderRuntime:
    """Create the active client/runtime tuple for the interview app."""
    configured_provider = str(secrets.get("API_PROVIDER", "openai"))
    configured_model = (
        ""
        if configured_provider.strip().lower() == "openrouter"
        else str(secrets.get("MODEL", "gpt-5.4"))
    )
    provider = normalize_provider(configured_provider, configured_model)
    model_selection = resolve_model_selection(
        provider, config_name, secrets, default_max_tokens
    )

    if provider == "openai":
        return ProviderRuntime(
            provider=provider,
            api="openai",
            client=OpenAI(api_key=secrets["API_KEY"]),
            model_selection=model_selection,
        )

    if provider == "deepinfra":
        return ProviderRuntime(
            provider=provider,
            api="openai",
            client=OpenAI(
                api_key=secrets["DEEPINFRA_API_KEY"],
                base_url="https://api.deepinfra.com/v1/openai",
            ),
            model_selection=model_selection,
        )

    if provider == "openrouter":
        headers = build_openrouter_headers(secrets)
        return ProviderRuntime(
            provider=provider,
            api="openai",
            client=OpenAI(
                api_key=secrets["OPENROUTER_API_KEY"],
                base_url=OPENROUTER_BASE_URL,
                default_headers=headers or None,
            ),
            model_selection=model_selection,
        )

    if provider == "anthropic":
        import anthropic  # noqa: E402

        return ProviderRuntime(
            provider=provider,
            api="anthropic",
            client=anthropic.Anthropic(api_key=secrets["ANTHROPIC_API_KEY"]),
            model_selection=model_selection,
        )

    raise ValueError(
        "Unrecognized API provider; supported values are openai, deepinfra, openrouter, and anthropic."
    )
