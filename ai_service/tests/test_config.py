"""Tests de la configuration du service IA."""

import pytest
from pydantic import ValidationError

from app.config import Settings


CONFIGURATION_VARIABLES = {
    "AI_SERVICE_HOST",
    "AI_SERVICE_PORT",
    "MCP_SERVER_URL",
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
    assert str(settings.mcp_server_url) == (
        "http://product-mcp-server:8000/mcp"
    )


def test_settings_read_environment(monkeypatch):
    """Lit les trois paramètres depuis l'environnement."""

    clear_configuration_environment(monkeypatch)
    monkeypatch.setenv("AI_SERVICE_HOST", "127.0.0.1")
    monkeypatch.setenv("AI_SERVICE_PORT", "9001")
    monkeypatch.setenv(
        "MCP_SERVER_URL",
        "http://mcp.test:8100/mcp",
    )

    settings = Settings()

    assert settings.ai_service_host == "127.0.0.1"
    assert settings.ai_service_port == 9001
    assert str(settings.mcp_server_url) == (
        "http://mcp.test:8100/mcp"
    )


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
        ("mcp_server_url", "ftp://mcp.test/mcp"),
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
