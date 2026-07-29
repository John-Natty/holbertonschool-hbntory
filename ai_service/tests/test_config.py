"""Tests de la configuration du service IA."""

import pytest
from pydantic import ValidationError

from app.config import Settings


CONFIGURATION_VARIABLES = {
    "AI_SERVICE_HOST",
    "AI_SERVICE_PORT",
    "CORS_ALLOWED_ORIGINS",
    "MCP_SERVER_URL",
    "MCP_REQUEST_TIMEOUT_SECONDS",
    "MCP_MAX_CONCURRENT_CALLS",
    "MCP_RECONNECT_ATTEMPTS",
    "MCP_RECONNECT_INITIAL_DELAY_SECONDS",
    "MCP_RECONNECT_MAX_DELAY_SECONDS",
    "CONVERSATION_TTL_SECONDS",
    "CONVERSATION_MAX_TURNS",
    "CONVERSATION_MAX_SESSIONS",
    "AI_MODEL_PROVIDER",
    "NVIDIA_API_KEY",
    "NVIDIA_BASE_URL",
    "NVIDIA_MODEL",
    "NVIDIA_REQUEST_TIMEOUT_SECONDS",
    "NVIDIA_CLASSIFICATION_MAX_TOKENS",
    "NVIDIA_ANSWER_MAX_TOKENS",
    "MINIMAX_API_KEY",
    "MINIMAX_BASE_URL",
    "MINIMAX_MODEL",
    "MINIMAX_REQUEST_TIMEOUT_SECONDS",
    "MINIMAX_CLASSIFICATION_MAX_TOKENS",
    "MINIMAX_ANSWER_MAX_TOKENS",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_REQUEST_TIMEOUT_SECONDS",
    "OLLAMA_CLASSIFICATION_MAX_TOKENS",
    "OLLAMA_ANSWER_MAX_TOKENS",
}


def clear_configuration_environment(monkeypatch) -> None:
    """Supprime les variables pouvant influencer les tests."""

    for variable_name in CONFIGURATION_VARIABLES:
        monkeypatch.delenv(
            variable_name,
            raising=False,
        )


def test_settings_use_docker_compose_defaults(monkeypatch):
    """Utilise des valeurs par défaut adaptées au réseau Compose."""

    clear_configuration_environment(monkeypatch)

    settings = Settings()

    assert settings.ai_service_host == "0.0.0.0"
    assert settings.ai_service_port == 8001
    assert settings.cors_allowed_origins == [
        "http://localhost:8080",
    ]
    assert str(settings.mcp_server_url) == (
        "http://product-mcp-server:8000/mcp"
    )
    assert settings.mcp_request_timeout_seconds == 10.0
    assert settings.mcp_max_concurrent_calls == 10
    assert settings.mcp_reconnect_attempts == 3
    assert settings.mcp_reconnect_initial_delay_seconds == 0.25
    assert settings.mcp_reconnect_max_delay_seconds == 2.0
    assert settings.conversation_ttl_seconds == 1800.0
    assert settings.conversation_max_turns == 10
    assert settings.conversation_max_sessions == 1000
    assert settings.ai_model_provider == "hybrid"
    assert settings.nvidia_api_key is None
    assert str(settings.nvidia_base_url) == (
        "https://integrate.api.nvidia.com/v1"
    )
    assert settings.nvidia_model == "minimaxai/minimax-m3"
    assert settings.nvidia_request_timeout_seconds == 120.0
    assert settings.nvidia_classification_max_tokens == 600
    assert settings.nvidia_answer_max_tokens == 1000
    assert settings.minimax_api_key is None
    assert str(settings.minimax_base_url) == (
        "https://api.minimax.io/v1"
    )
    assert settings.minimax_model == "MiniMax-M3"
    assert settings.minimax_request_timeout_seconds == 60.0
    assert settings.minimax_classification_max_tokens == 600
    assert settings.minimax_answer_max_tokens == 1000
    assert str(settings.ollama_base_url) == (
        "http://ollama:11434/"
    )
    assert settings.ollama_model == "gemma3:latest"
    assert settings.ollama_request_timeout_seconds == 60.0
    assert settings.ollama_classification_max_tokens == 600
    assert settings.ollama_answer_max_tokens == 1000


def test_settings_read_environment(monkeypatch):
    """Lit les trois paramètres depuis l'environnement."""

    clear_configuration_environment(monkeypatch)
    monkeypatch.setenv("AI_SERVICE_HOST", "127.0.0.1")
    monkeypatch.setenv("AI_SERVICE_PORT", "9001")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        (
            " http://localhost:8080, "
            "https://client.example:8443/ "
        ),
    )
    monkeypatch.setenv(
        "MCP_SERVER_URL",
        "http://mcp.test:8100/mcp",
    )
    monkeypatch.setenv(
        "MCP_REQUEST_TIMEOUT_SECONDS",
        "2.5",
    )
    monkeypatch.setenv(
        "MCP_MAX_CONCURRENT_CALLS",
        "4",
    )
    monkeypatch.setenv("MCP_RECONNECT_ATTEMPTS", "5")
    monkeypatch.setenv(
        "MCP_RECONNECT_INITIAL_DELAY_SECONDS",
        "0.1",
    )
    monkeypatch.setenv(
        "MCP_RECONNECT_MAX_DELAY_SECONDS",
        "1.5",
    )
    monkeypatch.setenv("CONVERSATION_TTL_SECONDS", "300")
    monkeypatch.setenv("CONVERSATION_MAX_TURNS", "4")
    monkeypatch.setenv("CONVERSATION_MAX_SESSIONS", "25")
    monkeypatch.setenv("AI_MODEL_PROVIDER", "ollama")
    monkeypatch.setenv(
        "OLLAMA_BASE_URL",
        "http://ollama.test:11435",
    )
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3:4b")
    monkeypatch.setenv(
        "OLLAMA_REQUEST_TIMEOUT_SECONDS",
        "7.5",
    )

    settings = Settings()

    assert settings.ai_service_host == "127.0.0.1"
    assert settings.ai_service_port == 9001
    assert settings.cors_allowed_origins == [
        "http://localhost:8080",
        "https://client.example:8443",
    ]
    assert str(settings.mcp_server_url) == (
        "http://mcp.test:8100/mcp"
    )
    assert settings.mcp_request_timeout_seconds == 2.5
    assert settings.mcp_max_concurrent_calls == 4
    assert settings.mcp_reconnect_attempts == 5
    assert settings.mcp_reconnect_initial_delay_seconds == 0.1
    assert settings.mcp_reconnect_max_delay_seconds == 1.5
    assert settings.conversation_ttl_seconds == 300.0
    assert settings.conversation_max_turns == 4
    assert settings.conversation_max_sessions == 25
    assert settings.ai_model_provider == "ollama"
    assert str(settings.ollama_base_url) == (
        "http://ollama.test:11435/"
    )
    assert settings.ollama_model == "gemma3:4b"
    assert settings.ollama_request_timeout_seconds == 7.5


def test_settings_reject_extra_field(monkeypatch):
    """Refuse un paramètre de configuration non déclaré."""

    clear_configuration_environment(monkeypatch)

    with pytest.raises(ValidationError):
        Settings(unexpected="value")


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("ai_service_host", "   "),
        ("ai_service_port", 0),
        ("ai_service_port", 65536),
        ("cors_allowed_origins", ""),
        ("cors_allowed_origins", " , "),
        ("cors_allowed_origins", "http://localhost:8080, "),
        ("cors_allowed_origins", "*"),
        ("cors_allowed_origins", "ftp://localhost:8080"),
        ("cors_allowed_origins", "http://localhost:8080/path"),
        ("cors_allowed_origins", []),
        ("mcp_server_url", "ftp://mcp.test/mcp"),
        ("mcp_request_timeout_seconds", 0),
        ("mcp_request_timeout_seconds", -1),
        ("mcp_request_timeout_seconds", True),
        ("mcp_request_timeout_seconds", float("inf")),
        ("mcp_request_timeout_seconds", float("nan")),
        ("mcp_max_concurrent_calls", 0),
        ("mcp_max_concurrent_calls", -1),
        ("mcp_max_concurrent_calls", True),
        ("mcp_reconnect_attempts", 0),
        ("mcp_reconnect_attempts", -1),
        ("mcp_reconnect_attempts", True),
        ("mcp_reconnect_initial_delay_seconds", -1),
        ("mcp_reconnect_initial_delay_seconds", True),
        ("mcp_reconnect_initial_delay_seconds", float("inf")),
        ("mcp_reconnect_initial_delay_seconds", float("nan")),
        ("mcp_reconnect_max_delay_seconds", -1),
        ("mcp_reconnect_max_delay_seconds", True),
        ("mcp_reconnect_max_delay_seconds", float("inf")),
        ("mcp_reconnect_max_delay_seconds", float("nan")),
        ("conversation_ttl_seconds", 0),
        ("conversation_ttl_seconds", True),
        ("conversation_ttl_seconds", float("inf")),
        ("conversation_ttl_seconds", 86_401),
        ("conversation_max_turns", 0),
        ("conversation_max_turns", True),
        ("conversation_max_turns", 51),
        ("conversation_max_sessions", 0),
        ("conversation_max_sessions", True),
        ("conversation_max_sessions", 10_001),
        ("ai_model_provider", "unknown"),
        ("ai_model_provider", "HYBRID"),
        ("ai_model_provider", "NVIDIA"),
        ("ai_model_provider", "MINIMAX"),
        ("nvidia_base_url", "ftp://nvidia.test"),
        ("nvidia_model", "   "),
        ("nvidia_request_timeout_seconds", 0),
        ("nvidia_request_timeout_seconds", -1),
        ("nvidia_request_timeout_seconds", True),
        ("nvidia_request_timeout_seconds", float("inf")),
        ("nvidia_request_timeout_seconds", float("nan")),
        ("nvidia_classification_max_tokens", 0),
        ("nvidia_classification_max_tokens", True),
        ("nvidia_classification_max_tokens", 8193),
        ("nvidia_answer_max_tokens", 0),
        ("nvidia_answer_max_tokens", True),
        ("nvidia_answer_max_tokens", 8193),
        ("minimax_base_url", "ftp://minimax.test"),
        ("minimax_model", "   "),
        ("minimax_request_timeout_seconds", 0),
        ("minimax_request_timeout_seconds", -1),
        ("minimax_request_timeout_seconds", True),
        ("minimax_request_timeout_seconds", float("inf")),
        ("minimax_request_timeout_seconds", float("nan")),
        ("minimax_classification_max_tokens", 0),
        ("minimax_classification_max_tokens", True),
        ("minimax_classification_max_tokens", 8193),
        ("minimax_answer_max_tokens", 0),
        ("minimax_answer_max_tokens", True),
        ("minimax_answer_max_tokens", 8193),
        ("ollama_base_url", "ftp://ollama.test"),
        ("ollama_model", "   "),
        ("ollama_request_timeout_seconds", 0),
        ("ollama_request_timeout_seconds", -1),
        ("ollama_request_timeout_seconds", True),
        ("ollama_request_timeout_seconds", float("inf")),
        ("ollama_request_timeout_seconds", float("nan")),
        ("ollama_classification_max_tokens", 0),
        ("ollama_classification_max_tokens", True),
        ("ollama_classification_max_tokens", 8193),
        ("ollama_answer_max_tokens", 0),
        ("ollama_answer_max_tokens", True),
        ("ollama_answer_max_tokens", 8193),
    ],
)
def test_settings_reject_invalid_values(
    monkeypatch,
    field_name,
    invalid_value,
):
    """Refuse les valeurs incompatibles avec le service HTTP."""

    clear_configuration_environment(monkeypatch)

    with pytest.raises(ValidationError):
        Settings(
            **{
                field_name: invalid_value,
            }
        )


def test_settings_reject_reconnect_max_below_initial(
    monkeypatch,
) -> None:
    """Refuse un plafond de backoff inférieur au délai initial."""

    clear_configuration_environment(monkeypatch)

    with pytest.raises(ValidationError):
        Settings(
            mcp_reconnect_initial_delay_seconds=1,
            mcp_reconnect_max_delay_seconds=0.5,
        )


def test_blank_provider_keys_are_absent(
    monkeypatch,
) -> None:
    """Autorise Compose à transmettre des variables optionnelles vides."""

    clear_configuration_environment(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "   ")
    monkeypatch.setenv("MINIMAX_API_KEY", "   ")

    settings = Settings()

    assert settings.nvidia_api_key is None
    assert settings.minimax_api_key is None
