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
    "AI_INTENT_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_REQUEST_TIMEOUT_SECONDS",
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
    assert settings.ai_intent_provider == "rules"
    assert str(settings.ollama_base_url) == (
        "http://ollama:11434/"
    )
    assert settings.ollama_model == "gemma3:latest"
    assert settings.ollama_request_timeout_seconds == 30.0


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
    monkeypatch.setenv("AI_INTENT_PROVIDER", "ollama")
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
    assert settings.ai_intent_provider == "ollama"
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
        ("ai_intent_provider", "unknown"),
        ("ai_intent_provider", "OLLAMA"),
        ("ollama_base_url", "ftp://ollama.test"),
        ("ollama_model", "   "),
        ("ollama_request_timeout_seconds", 0),
        ("ollama_request_timeout_seconds", -1),
        ("ollama_request_timeout_seconds", True),
        ("ollama_request_timeout_seconds", float("inf")),
        ("ollama_request_timeout_seconds", float("nan")),
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
