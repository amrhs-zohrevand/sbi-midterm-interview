from dataclasses import dataclass

from openai import OpenAI


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "qwen/qwen3.5-35b-a3b"
OPENROUTER_INDUSTRY_MODEL = "openai/gpt-5.4"
OPENROUTER_DEFAULT_REASONING_EFFORT = "minimal"
OPENROUTER_MIN_REASONING_MAX_TOKENS = 1536
OPENROUTER_INDUSTRY_CONFIGS = {"industry_org_survey"}
OPENROUTER_REASONING_EFFORTS = {"minimal", "low", "medium", "high"}


@dataclass(frozen=True)
class ModelSelection:
    model: str
    max_tokens: int
    reasoning: dict | None = None
    verbosity: str | None = None


@dataclass(frozen=True)
class ProviderRuntime:
    provider: str
    api: str
    client: object
    model_selection: ModelSelection


def normalize_provider(provider_name: str, model_name: str = "") -> str:
    """Normalize the configured provider name for downstream branching."""
    provider = (provider_name or "openai").strip().lower()
    if provider == "anthropic" or "claude" in model_name.lower():
        return "anthropic"
    return provider


def _normalize_reasoning_effort(raw_effort: str) -> str:
    effort = (raw_effort or OPENROUTER_DEFAULT_REASONING_EFFORT).strip().lower()
    if effort not in OPENROUTER_REASONING_EFFORTS:
        return OPENROUTER_DEFAULT_REASONING_EFFORT
    return effort


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
    if model_selection.verbosity:
        updated["verbosity"] = model_selection.verbosity
    if model_selection.reasoning:
        updated["extra_body"] = {"reasoning": dict(model_selection.reasoning)}
    return updated


def resolve_model_selection(provider: str, config_name: str, secrets, default_max_tokens: int) -> ModelSelection:
    """Select the active model and request settings for the given provider/config."""
    if provider != "openrouter":
        return ModelSelection(
            model=str(secrets.get("MODEL", "gpt-3.5-turbo")),
            max_tokens=default_max_tokens,
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
            reasoning={"effort": reasoning_effort, "exclude": True},
            verbosity=str(secrets.get("OPENROUTER_INDUSTRY_VERBOSITY", "low")),
        )

    return ModelSelection(
        model=str(secrets.get("OPENROUTER_DEFAULT_MODEL", OPENROUTER_DEFAULT_MODEL)),
        max_tokens=default_max_tokens,
        reasoning={"enabled": False},
    )


def create_provider_runtime(secrets, config_name: str, default_max_tokens: int) -> ProviderRuntime:
    """Create the active client/runtime tuple for the interview app."""
    configured_provider = str(secrets.get("API_PROVIDER", "openai"))
    configured_model = str(secrets.get("MODEL", "gpt-3.5-turbo"))
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
