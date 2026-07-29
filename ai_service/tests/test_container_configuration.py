"""Tests statiques ciblés de l'intégration Docker du service IA."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE_ROOT = REPOSITORY_ROOT / "ai_service"
CLIENT_WEB_ROOT = REPOSITORY_ROOT / "client_web"


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
    assert "11434" not in dockerfile
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


def test_compose_ai_service_configures_nvidia_without_secret() -> None:
    """Contrôle NVIDIA, MCP et l'absence de secrets internes."""

    service = _compose_service_block("ai-service")

    assert "context: ./ai_service" in service
    assert "AI_SERVICE_HOST: 0.0.0.0" in service
    assert "AI_SERVICE_PORT: 8001" in service
    assert (
        "CORS_ALLOWED_ORIGINS: "
        "${CORS_ALLOWED_ORIGINS:-http://localhost:8080}"
        in service
    )
    assert (
        "MCP_SERVER_URL: http://product-mcp-server:8000/mcp"
        in service
    )
    assert "MCP_RECONNECT_ATTEMPTS: 3" in service
    assert "MCP_RECONNECT_INITIAL_DELAY_SECONDS: 0.25" in service
    assert "MCP_RECONNECT_MAX_DELAY_SECONDS: 2" in service
    assert (
        "CONVERSATION_TTL_SECONDS: "
        "${CONVERSATION_TTL_SECONDS:-1800}"
        in service
    )
    assert (
        "CONVERSATION_MAX_TURNS: "
        "${CONVERSATION_MAX_TURNS:-10}"
        in service
    )
    assert (
        "CONVERSATION_MAX_SESSIONS: "
        "${CONVERSATION_MAX_SESSIONS:-1000}"
        in service
    )
    assert "AI_MODEL_PROVIDER: ${AI_MODEL_PROVIDER:-nvidia}" in service
    assert "NVIDIA_API_KEY: ${NVIDIA_API_KEY:-}" in service
    assert (
        "NVIDIA_BASE_URL: "
        "${NVIDIA_BASE_URL:-https://integrate.api.nvidia.com/v1}"
        in service
    )
    assert (
        "NVIDIA_MODEL: ${NVIDIA_MODEL:-minimaxai/minimax-m3}"
        in service
    )
    assert (
        "NVIDIA_REQUEST_TIMEOUT_SECONDS: "
        "${NVIDIA_REQUEST_TIMEOUT_SECONDS:-60}"
        in service
    )
    assert (
        "NVIDIA_CLASSIFICATION_MAX_TOKENS: "
        "${NVIDIA_CLASSIFICATION_MAX_TOKENS:-600}"
        in service
    )
    assert (
        "NVIDIA_ANSWER_MAX_TOKENS: "
        "${NVIDIA_ANSWER_MAX_TOKENS:-1000}"
        in service
    )
    assert "${AI_SERVICE_HOST_PORT:-8001}:8001" in service
    assert "product-mcp-server:" in service
    assert "condition: service_started" in service
    assert "11434" not in service
    assert "http://localhost:8001/health" in service
    assert "http://localhost:8001/ready" not in service
    assert "DATABASE_URL" not in service
    assert "POSTGRES_" not in service
    assert "INTERNAL_API_KEY" not in service
    assert "env_file:" not in service
    assert "volumes:" not in service


def test_compose_contains_no_local_model_service_or_volume() -> None:
    """Vérifie que la pile ne démarre ni modèle local ni volume associé."""

    compose = REPOSITORY_ROOT.joinpath(
        "docker-compose.yml"
    ).read_text(encoding="utf-8")
    assert "11434" not in compose
    assert "ollama" not in compose.lower()


def test_client_catalog_keeps_conversation_and_bypasses_generation() -> None:
    """Vérifie l'intégration des cartes avec le contrat IA moderne."""

    html = CLIENT_WEB_ROOT.joinpath("index.html").read_text(
        encoding="utf-8"
    )
    script = CLIENT_WEB_ROOT.joinpath("script.js").read_text(
        encoding="utf-8"
    )
    dockerfile = CLIENT_WEB_ROOT.joinpath("Dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'id="catalog-grid"' in html
    assert 'id="catalog-list"' not in html
    assert "COPY img/ /usr/share/nginx/html/img/" in dockerfile
    assert CLIENT_WEB_ROOT.joinpath(
        "img/categories/default.webp"
    ).is_file()
    assert "const catalogGrid" in script
    assert "buildProductCard(product)" in script
    assert "CONVERSATION_STORAGE_KEY" in script
    assert "sessionStorage.getItem" in script
    assert "sessionStorage.setItem" in script
    assert (
        'AI_PRODUCTS_URL + "?limit=100&offset=0"'
        in script
    )
    assert 'askQuestion("liste les 100 premiers produits")' not in script
    assert 'data.type === "stock_by_product"' not in script
