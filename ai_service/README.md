# Service IA HBntory

Ce service expose l’API REST asynchrone utilisée par le futur client web.
Il est indépendant du Backoffice, de PostgreSQL et de l’API Produit.

## État actuel

Le service possède un client officiel MCP Streamable HTTP. Une seule session
est initialisée pendant le lifespan FastAPI, vérifie les cinq outils attendus,
puis est partagée jusqu'à sa fermeture propre à l'arrêt.

L'orchestration et le modèle IA ne sont pas encore intégrés. `POST /query`
continue donc à utiliser `UnavailableQueryService` et retourne temporairement
une erreur structurée `503 service_unavailable`, sans appeler MCP.

Routes disponibles :

- `GET /health` : état du processus HTTP ;
- `GET /ready` : disponibilité de la session MCP, avec `200` ou `503` ;
- `POST /query` : validation et traitement injectable d'une question.

## Installation

```bash
cd ai_service

uv venv .venv --python 3.12

uv pip install \
  --python .venv/bin/python \
  -r requirements.txt \
  -r requirements-dev.txt
```

## Configuration

Valeurs par défaut :

```text
AI_SERVICE_HOST=0.0.0.0
AI_SERVICE_PORT=8001
MCP_SERVER_URL=http://product-mcp-server:8000/mcp
MCP_REQUEST_TIMEOUT_SECONDS=10
MCP_MAX_CONCURRENT_CALLS=10
```

La connexion Streamable HTTP est créée au démarrage du lifespan, jamais au
simple chargement d'un module. Si MCP est indisponible, `/health` reste
accessible et `/ready` retourne `503`.

## Lancement local

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m app.main
```

## Tests

Les tests utilisent directement l'application ASGI et des doubles injectés
autour du transport et de la session MCP, sans serveur ni réseau :

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider
```

La phase suivante reliera `POST /query` aux cinq méthodes typées du client,
sans accès direct au Backoffice, à l'API Produit ou à PostgreSQL.
