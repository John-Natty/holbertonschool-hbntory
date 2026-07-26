"""Tests statiques ciblés de l'intégration Docker du service IA."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE_ROOT = REPOSITORY_ROOT / "ai_service"


def _compose_service_block(service_name: str) -> str:
    """Extrait un bloc de service sans dépendre d'un parseur YAML."""

    lines = (
        REPOSITORY_ROOT
        .joinpath("docker-compose.yml")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    header = f"  {service_name}:"
    start = lines.index(header)
    block = [lines[start]]

    for line in lines[start + 1:]:
        if (
            line.startswith("  ")
            and not line.startswith("    ")
            and line.endswith(":")
        ):
            break

        if line and not line.startswith(" "):
            break

        block.append(line)

    return "\n".join(block)


def test_ai_dockerfile_is_production_only_and_non_root() -> None:
    """Vérifie l'image, les copies, l'utilisateur et la commande."""

    dockerfile = AI_SERVICE_ROOT.joinpath("Dockerfile").read_text(
        encoding="utf-8"
    )

    assert dockerfile.startswith("FROM python:3.12-slim\n")
    assert "COPY requirements.txt ." in dockerfile
    assert "COPY --chown=ai-service:ai-service app ./app" in dockerfile
    assert "COPY . ." not in dockerfile
    assert "requirements-dev.txt" not in dockerfile
    assert "pytest" not in dockerfile
    assert "USER ai-service:ai-service" in dockerfile
    assert "EXPOSE 8001" in dockerfile
    assert "http://localhost:8001/health" in dockerfile
    assert "--reload" not in dockerfile
    assert "ollama pull" not in dockerfile
    assert (
        'CMD ["python", "-m", "uvicorn", "app.main:app", '
        '"--host", "0.0.0.0", "--port", "8001"]'
        in dockerfile
    )


def test_ai_dockerignore_excludes_local_and_test_files() -> None:
    """Empêche l'envoi des fichiers locaux inutiles au build."""

    entries = {
        line.strip().rstrip("/")
        for line in AI_SERVICE_ROOT
        .joinpath(".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    assert {
        ".venv",
        "__pycache__",
        "*.py[cod]",
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        ".env",
        ".git",
        "tests",
        "requirements-dev.txt",
    } <= entries


def test_compose_ai_service_uses_only_internal_mcp_and_ollama_urls() -> None:
    """Contrôle les variables et dépendances du service IA."""

    service = _compose_service_block("ai-service")

    assert "context: ./ai_service" in service
    assert "AI_SERVICE_HOST: 0.0.0.0" in service
    assert "AI_SERVICE_PORT: 8001" in service
    assert (
        "MCP_SERVER_URL: http://product-mcp-server:8000/mcp"
        in service
    )
    assert "MCP_RECONNECT_ATTEMPTS: 3" in service
    assert "MCP_RECONNECT_INITIAL_DELAY_SECONDS: 0.25" in service
    assert "MCP_RECONNECT_MAX_DELAY_SECONDS: 2" in service
    assert "AI_INTENT_PROVIDER: ${AI_INTENT_PROVIDER:-rules}" in service
    assert "OLLAMA_BASE_URL: http://ollama:11434" in service
    assert "OLLAMA_MODEL: ${OLLAMA_MODEL:-gemma3:latest}" in service
    assert "${AI_SERVICE_HOST_PORT:-8001}:8001" in service
    assert "product-mcp-server:" in service
    assert "condition: service_started" in service
    assert "condition: service_healthy" not in service
    assert "\n      ollama:" not in service
    assert "http://localhost:8001/health" in service
    assert "http://localhost:8001/ready" not in service
    assert "DATABASE_URL" not in service
    assert "POSTGRES_" not in service
    assert "INTERNAL_API_KEY" not in service
    assert "env_file:" not in service
    assert "volumes:" not in service


def test_compose_ollama_is_optional_and_persists_only_models() -> None:
    """Vérifie le profil, le healthcheck et le volume Ollama."""

    compose = REPOSITORY_ROOT.joinpath(
        "docker-compose.yml"
    ).read_text(encoding="utf-8")
    service = _compose_service_block("ollama")

    assert "image: ollama/ollama:" in service
    assert "profiles:" in service
    assert "- ollama" in service
    assert "11434}:11434" in service
    assert "ollama-data:/root/.ollama" in service
    assert "- ollama\n        - list" in service
    assert "ollama pull" not in compose
    assert "\n  ollama-data:" in compose
